from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth import login, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Case, Count, IntegerField, Q, When, Value
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    BookingForm, CategoryAdminForm, ComplaintAdminForm, ComplaintForm, ListingAdminForm,
    ProfileForm, ProviderProfileForm, ReviewForm,
    ServiceListingForm, SignupForm, TeamAdminCreateForm, TeamAdminPasswordChangeForm,
    TeamAdminPasswordResetForm, TeamAdminUpdateForm, StaffLoginForm, StaffProfileForm,
    team_permission_queryset,
)
from .models import (
    AdminAuditLog, Booking, BookingStatusHistory, Category, Complaint, Notification,
    Profile, ProviderProfile, Review, ServiceListing, TeamAdminAccount,
)


def primary_admin_required(view_func):
    @wraps(view_func)
    @login_required(login_url='staff_login')
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def staff_permission_required(permission):
    def decorate(view_func):
        @wraps(view_func)
        @login_required(login_url='staff_login')
        def wrapped(request, *args, **kwargs):
            if not request.user.is_staff or not (
                request.user.is_superuser or request.user.has_perm(f'core.{permission}')
            ):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorate


def admin_landing_url(user):
    if user.is_superuser or user.has_perm('core.view_findora_dashboard'):
        return reverse('staff_dashboard')
    for permission, route in (
        ('view_category', 'staff_categories'),
        ('view_servicelisting', 'staff_listings'),
        ('view_providerprofile', 'staff_providers'),
        ('view_profile', 'staff_customers'),
        ('view_booking', 'staff_bookings'),
        ('view_review', 'staff_reviews'),
        ('view_complaint', 'staff_complaints'),
    ):
        if user.has_perm(f'core.{permission}'):
            return reverse(route)
    return reverse('staff_login')


def log_admin_action(request, action, target, summary):
    AdminAuditLog.objects.create(
        actor=request.user,
        action=action,
        object_type=target._meta.label_lower,
        object_id=str(target.pk),
        summary=summary,
    )


def staff_login(request):
    if request.user.is_authenticated:
        if not request.user.is_staff:
            raise PermissionDenied
        return redirect(admin_landing_url(request.user))

    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        allowed_staff = user.is_superuser or any(
            permission.startswith('core.') for permission in user.get_all_permissions()
        )
        if not user.is_staff or not allowed_staff:
            form.add_error(None, 'This account is not authorized to use Findora administration.')
        else:
            login(request, user)
            next_url = request.POST.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ) and next_url.startswith('/staff/'):
                return redirect(next_url)
            return redirect(admin_landing_url(user))
    return render(request, 'core/staff_login.html', {
        'form': form,
        'next': request.POST.get('next', request.GET.get('next', '')),
    })


@login_required(login_url='staff_login')
def staff_profile(request):
    if not request.user.is_staff or not (
        request.user.is_superuser or any(
            permission.startswith('core.') for permission in request.user.get_all_permissions()
        )
    ):
        raise PermissionDenied

    form = StaffProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your administrator profile has been updated.')
        return redirect('staff_profile')
    return render(request, 'core/staff_profile.html', {'form': form})


def home(request):
    categories = Category.objects.filter(is_active=True)
    listings = recommended_listings(request).select_related('provider', 'category')[:6]
    return render(request, 'core/home.html', {'categories': categories, 'listings': listings})


def about(request):
    return render(request, 'core/about.html')


def recommended_listings(request):
    listings = ServiceListing.objects.filter(
        is_active=True, provider__provider_profile__verified=True,
    ).annotate(
        avg_rating=Avg('bookings__review__rating', filter=Q(bookings__review__is_public=True)),
        review_count=Count('bookings__review', filter=Q(bookings__review__is_public=True)),
    )
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = None
        if profile and profile.locality:
            listings = listings.annotate(local_match=Case(
                When(Q(service_area__icontains=profile.locality) |
                     Q(provider__provider_profile__service_areas__icontains=profile.locality), then=Value(1)),
                default=Value(0), output_field=IntegerField(),
            )).order_by('-local_match', '-avg_rating', '-review_count', 'title')
            return listings
    return listings.order_by('-avg_rating', '-review_count', 'title')


def service_list(request):
    listings = ServiceListing.objects.filter(
        is_active=True, provider__provider_profile__verified=True,
    ).select_related('provider', 'category').annotate(
        avg_rating=Avg('bookings__review__rating', filter=Q(bookings__review__is_public=True)),
    )
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    locality = request.GET.get('locality', '').strip()
    filter_errors = []
    if query:
        listings = listings.filter(Q(title__icontains=query) | Q(provider__first_name__icontains=query) |
                                   Q(provider__last_name__icontains=query) |
                                   Q(provider__provider_profile__business_name__icontains=query))
    if category:
        if category.isdigit():
            listings = listings.filter(category_id=int(category))
        else:
            filter_errors.append('The selected category was invalid and has been ignored.')
    if locality:
        listings = listings.filter(Q(service_area__icontains=locality) |
                                   Q(provider__provider_profile__service_areas__icontains=locality))
    min_experience = request.GET.get('min_experience', '').strip()
    if min_experience:
        try:
            experience_value = int(min_experience)
            if experience_value < 0:
                raise ValueError
            listings = listings.filter(provider__provider_profile__experience_years__gte=experience_value)
        except ValueError:
            filter_errors.append('Minimum experience must be a non-negative whole number.')
    if request.GET.get('available') == '1':
        listings = listings.exclude(provider__provider_profile__availability='')
    min_rating = request.GET.get('min_rating', '').strip()
    if min_rating:
        try:
            rating_value = int(min_rating)
            if rating_value not in range(1, 6):
                raise ValueError
            listings = listings.filter(avg_rating__gte=rating_value)
        except ValueError:
            filter_errors.append('Minimum rating must be between 1 and 5.')
    price_values = {}
    for price_filter, lookup in (('min_price', 'gte'), ('max_price', 'lte')):
        price = request.GET.get(price_filter, '').strip()
        if price:
            try:
                amount = Decimal(price)
                if not amount.is_finite() or amount < 0:
                    raise InvalidOperation
                price_values[price_filter] = amount
            except InvalidOperation:
                filter_errors.append('Price filters must be valid non-negative amounts.')
    if price_values.get('min_price') is not None and price_values.get('max_price') is not None:
        if price_values['min_price'] > price_values['max_price']:
            filter_errors.append('Minimum price cannot be higher than maximum price.')
            price_values = {}
    for price_filter, lookup in (('min_price', 'gte'), ('max_price', 'lte')):
        if price_filter in price_values:
            listings = listings.filter(price_from__isnull=False, **{f'price_from__{lookup}': price_values[price_filter]})
    paginator = Paginator(listings.order_by('-avg_rating', 'title'), 9)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/service_list.html', {
        'page_obj': page, 'categories': Category.objects.filter(is_active=True),
        'query': query, 'selected_category': category, 'locality': locality,
        'filter_errors': filter_errors,
    })


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    return render(request, 'core/category_detail.html', {
        'category': category,
        'listings': ServiceListing.objects.filter(category=category, is_active=True,
            provider__provider_profile__verified=True).select_related('provider', 'provider__provider_profile')
            .annotate(avg_rating=Avg('bookings__review__rating', filter=Q(bookings__review__is_public=True)))
            .order_by('-avg_rating'),
    })


def provider_detail(request, provider_id):
    provider = get_object_or_404(ProviderProfile.objects.select_related('user'), user_id=provider_id, verified=True)
    listings = ServiceListing.objects.filter(provider=provider.user, is_active=True).select_related('category').annotate(
        avg_rating=Avg('bookings__review__rating', filter=Q(bookings__review__is_public=True)))
    return render(request, 'core/provider_detail.html', {'provider': provider, 'listings': listings})


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    requested_role = request.GET.get('role')
    initial = {'role': requested_role} if requested_role in Profile.Role.values else None
    form = SignupForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            role = form.cleaned_data['role']
            Profile.objects.create(user=user, role=role)
            if role == Profile.Role.PROVIDER:
                ProviderProfile.objects.create(user=user)
            login(request, user)
        messages.success(request, 'Your Findora account is ready.')
        return redirect('home')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Create your account', 'submit_label': 'Register'})


@login_required
def dashboard(request):
    profile = getattr(request.user, 'profile', None)
    if request.user.is_staff:
        return redirect(admin_landing_url(request.user))
    if profile is None:
        raise Http404
    if profile and profile.role == Profile.Role.PROVIDER:
        provider_profile = getattr(request.user, 'provider_profile', None)
        bookings = Booking.objects.filter(listing__provider=request.user).select_related('customer', 'listing')
        return render(request, 'core/provider_dashboard.html', {
            'provider_profile': provider_profile,
            'incoming': bookings.filter(status=Booking.Status.PENDING)[:6],
            'request_count': bookings.filter(status=Booking.Status.PENDING).count(),
            'bookings': bookings[:8],
            'active_bookings': bookings.filter(
                status__in=[Booking.Status.ACCEPTED, Booking.Status.IN_PROGRESS]
            ).order_by('preferred_date', 'preferred_time')[:5],
            'listings': ServiceListing.objects.filter(provider=request.user).select_related('category'),
            'active_count': bookings.filter(status__in=[Booking.Status.ACCEPTED, Booking.Status.IN_PROGRESS]).count(),
            'completed_count': bookings.filter(status=Booking.Status.COMPLETED).count(),
            'reviews': Review.objects.filter(booking__listing__provider=request.user, is_public=True)
                .select_related('booking', 'booking__customer').order_by('-created_at')[:6],
            'verified': bool(provider_profile and provider_profile.verified),
        })
    return render(request, 'core/customer_dashboard.html', {
        'bookings': Booking.objects.filter(customer=request.user).select_related('listing', 'listing__provider')[:6],
        'booking_count': Booking.objects.filter(customer=request.user).count(),
        'pending_count': Booking.objects.filter(customer=request.user, status=Booking.Status.PENDING).count(),
        'completed_count': Booking.objects.filter(customer=request.user, status=Booking.Status.COMPLETED).count(),
        'notifications': request.user.notifications.all()[:5],
        'reviews': Review.objects.filter(booking__customer=request.user, is_public=True)
            .select_related('booking', 'booking__listing', 'booking__listing__provider')
            .order_by('-created_at')[:5],
    })


@login_required
def profile_update(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile, initial={
        'first_name': request.user.first_name, 'last_name': request.user.last_name, 'email': request.user.email,
    })
    if request.method == 'POST' and form.is_valid():
        request.user.first_name = form.cleaned_data['first_name']
        request.user.last_name = form.cleaned_data['last_name']
        request.user.email = form.cleaned_data['email']
        request.user.save()
        form.save()
        messages.success(request, 'Your profile has been updated.')
        return redirect('dashboard')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Your profile', 'submit_label': 'Save profile'})


@login_required
def provider_profile_update(request):
    if not hasattr(request.user, 'profile') or request.user.profile.role != Profile.Role.PROVIDER:
        raise Http404
    provider_profile, _ = ProviderProfile.objects.get_or_create(user=request.user)
    form = ProviderProfileForm(request.POST or None, instance=provider_profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your professional profile has been saved. Verification is managed by Findora administrators.')
        return redirect('dashboard')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Professional profile', 'submit_label': 'Save profile'})


@login_required
def listing_create(request):
    if not hasattr(request.user, 'profile') or request.user.profile.role != Profile.Role.PROVIDER:
        raise Http404
    form = ServiceListingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        listing = form.save(commit=False)
        listing.provider = request.user
        listing.save()
        messages.success(request, 'Your service listing has been created.')
        return redirect('dashboard')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Add a service', 'submit_label': 'Create listing'})


@login_required
def listing_update(request, listing_id):
    if not hasattr(request.user, 'profile') or request.user.profile.role != Profile.Role.PROVIDER:
        raise Http404
    listing = get_object_or_404(ServiceListing, pk=listing_id, provider=request.user)
    form = ServiceListingForm(request.POST or None, instance=listing)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your service listing has been updated.')
        return redirect('dashboard')
    return render(request, 'core/form_page.html', {
        'form': form, 'title': 'Edit service listing', 'submit_label': 'Save changes',
    })


@login_required
def booking_create(request, booking_id):
    if not hasattr(request.user, 'profile') or request.user.profile.role != Profile.Role.CUSTOMER:
        raise Http404
    listing = get_object_or_404(ServiceListing, pk=booking_id, is_active=True, provider__provider_profile__verified=True)
    if listing.provider_id == request.user.id:
        raise Http404
    form = BookingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        booking = form.save(commit=False)
        booking.customer = request.user
        booking.listing = listing
        with transaction.atomic():
            booking.save()
            Notification.objects.create(recipient=listing.provider, message=f'New request for {listing.title}.', link='/bookings/')
        messages.success(request, 'Your request has been sent to the provider.')
        return redirect('booking_list')
    return render(request, 'core/form_page.html', {'form': form, 'title': f'Request {listing.title}', 'submit_label': 'Send request'})


@login_required
def booking_list(request):
    if request.user.is_staff:
        if not (
            request.user.is_superuser
            or request.user.has_perm('core.view_booking')
            or request.user.has_perm('core.change_booking')
        ):
            raise PermissionDenied
        bookings = Booking.objects.all()
    elif hasattr(request.user, 'profile') and request.user.profile.role == Profile.Role.PROVIDER:
        bookings = Booking.objects.filter(listing__provider=request.user)
    elif hasattr(request.user, 'profile') and request.user.profile.role == Profile.Role.CUSTOMER:
        bookings = Booking.objects.filter(customer=request.user)
    else:
        raise Http404
    return render(request, 'core/booking_list.html', {
        'bookings': bookings.select_related('customer', 'listing', 'listing__provider').order_by('-created_at'),
    })


@login_required
@require_POST
def booking_transition(request, booking_id):
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update().select_related('listing'),
                                    pk=booking_id)
        role = getattr(getattr(request.user, 'profile', None), 'role', None)
        is_provider = role == Profile.Role.PROVIDER and booking.listing.provider_id == request.user.id
        is_customer = role == Profile.Role.CUSTOMER and booking.customer_id == request.user.id
        action = request.POST.get('action')
        transitions = {
            ('pending', 'accept', True): Booking.Status.ACCEPTED,
            ('pending', 'reject', True): Booking.Status.REJECTED,
            ('accepted', 'start', True): Booking.Status.IN_PROGRESS,
            ('in_progress', 'complete', True): Booking.Status.COMPLETED,
        }
        new_status = transitions.get((booking.status, action, is_provider))
        if action == 'cancel' and is_customer and booking.status in {Booking.Status.PENDING, Booking.Status.ACCEPTED}:
            new_status = Booking.Status.CANCELLED
        if not new_status:
            raise Http404
        old_status = booking.status
        booking.status = new_status
        booking.save(update_fields=['status', 'updated_at'])
        BookingStatusHistory.objects.create(
            booking=booking,
            previous_status=old_status,
            new_status=new_status,
            changed_by=request.user,
        )
        recipient = booking.customer if is_provider else booking.listing.provider
        Notification.objects.create(recipient=recipient, message=f'Booking status changed to {booking.get_status_display()}.',
                                   link='/bookings/')
    messages.success(request, f'Booking updated: {booking.get_status_display()}.')
    return redirect('booking_list')


@login_required
def review_create(request, booking_id):
    if not hasattr(request.user, 'profile') or request.user.profile.role != Profile.Role.CUSTOMER:
        raise Http404
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user, status=Booking.Status.COMPLETED)
    if hasattr(booking, 'review'):
        messages.info(request, 'You have already reviewed this service.')
        return redirect('booking_list')
    form = ReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        review = form.save(commit=False)
        review.booking = booking
        with transaction.atomic():
            review, created = Review.objects.get_or_create(
                booking=booking,
                defaults={'rating': review.rating, 'comment': review.comment},
            )
            if not created:
                messages.info(request, 'You have already reviewed this service.')
                return redirect('booking_list')
            Notification.objects.create(recipient=booking.listing.provider, message='A customer left feedback on a completed service.', link='/dashboard/')
        messages.success(request, 'Thank you for sharing your feedback.')
        return redirect('booking_list')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Review your service', 'submit_label': 'Submit review'})


@login_required
def complaint_create(request):
    if request.user.is_staff:
        raise PermissionDenied
    if not hasattr(request.user, 'profile'):
        raise Http404
    form = ComplaintForm(request.POST or None)
    form.fields['booking'].queryset = Booking.objects.filter(
        Q(customer=request.user) | Q(listing__provider=request.user)
    )
    if request.method == 'POST' and form.is_valid():
        complaint = form.save(commit=False)
        complaint.submitted_by = request.user
        complaint.save()
        messages.success(request, 'Your feedback has been submitted for review.')
        return redirect('dashboard')
    return render(request, 'core/form_page.html', {'form': form, 'title': 'Contact Findora support', 'submit_label': 'Send feedback'})


@login_required
def notifications(request):
    return render(request, 'core/notifications.html', {'notifications': request.user.notifications.all()})


@login_required
@require_POST
def mark_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, 'Your notifications are marked as read.')
    return redirect('notifications')


def _admin_list_page(request, queryset, page_size=20):
    return Paginator(queryset, page_size).get_page(request.GET.get('page'))


@staff_permission_required('view_category')
def staff_categories(request):
    if request.method == 'POST':
        action_errors = None
        if request.POST.get('action') == 'create':
            if not (request.user.is_superuser or request.user.has_perm('core.add_category')):
                raise PermissionDenied
            form = CategoryAdminForm(request.POST)
            if form.is_valid():
                category = form.save()
                log_admin_action(request, 'create', category, 'Created service category.')
                messages.success(request, 'Service category created.')
                return redirect('staff_categories')
            action_errors = form.errors
        elif request.POST.get('category_id'):
            if not (request.user.is_superuser or request.user.has_perm('core.change_category')):
                raise PermissionDenied
            category = get_object_or_404(Category, pk=request.POST.get('category_id'))
            form = CategoryAdminForm(request.POST, instance=category)
            if form.is_valid():
                category = form.save()
                log_admin_action(request, 'update', category, 'Updated service category.')
                messages.success(request, 'Service category updated.')
                return redirect('staff_categories')
            action_errors = form.errors
        else:
            form = CategoryAdminForm()
            form.add_error(None, 'Choose a category action.')
            action_errors = form.errors
        messages.error(request, 'The category was not saved. Check the highlighted form errors.')
    else:
        form = CategoryAdminForm()
        action_errors = None
    query = request.GET.get('q', '').strip()
    active = request.GET.get('active', '')
    categories = Category.objects.annotate(listing_count=Count('listings')).order_by('name')
    if query:
        categories = categories.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if active in ('true', 'false'):
        categories = categories.filter(is_active=(active == 'true'))
    categories = categories.annotate(provider_count=Count('listings__provider', distinct=True))
    return render(request, 'core/staff_categories.html', {
        'form': form,
        'action_errors': action_errors,
        'categories': _admin_list_page(request, categories),
        'query': query,
        'active_filter': active,
        'can_add': request.user.is_superuser or request.user.has_perm('core.add_category'),
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_category'),
    })


@staff_permission_required('view_servicelisting')
def staff_listings(request):
    form = ListingAdminForm(request.POST or None, prefix='create')
    if request.method == 'POST':
        if not (request.user.is_superuser or request.user.has_perm('core.add_servicelisting')):
            raise PermissionDenied
        if form.is_valid():
            listing = form.save()
            log_admin_action(request, 'create', listing, 'Created service listing.')
            messages.success(request, 'Service listing created.')
            return redirect('staff_listings')
        messages.error(request, 'The listing was not saved. Check the form errors.')
    listings = ServiceListing.objects.select_related('provider', 'category').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '')
    provider_id = request.GET.get('provider', '')
    if query:
        listings = listings.filter(
            Q(title__icontains=query) | Q(provider__username__icontains=query) |
            Q(category__name__icontains=query) | Q(service_area__icontains=query)
        )
    if category_id.isdigit():
        listings = listings.filter(category_id=int(category_id))
    if provider_id.isdigit():
        listings = listings.filter(provider_id=int(provider_id))
    return render(request, 'core/staff_listings.html', {
        'form': form,
        'listings': _admin_list_page(request, listings),
        'categories': Category.objects.order_by('name'),
        'query': query,
        'selected_category': category_id,
        'selected_provider': provider_id,
        'can_add': request.user.is_superuser or request.user.has_perm('core.add_servicelisting'),
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_servicelisting'),
    })


@staff_permission_required('view_servicelisting')
def staff_listing_edit(request, listing_id):
    listing = get_object_or_404(ServiceListing.objects.select_related('provider', 'category'), pk=listing_id)
    if not (request.user.is_superuser or request.user.has_perm('core.change_servicelisting')):
        raise PermissionDenied
    form = ListingAdminForm(request.POST or None, instance=listing)
    if request.method == 'POST' and form.is_valid():
        listing = form.save()
        log_admin_action(request, 'update', listing, 'Updated service listing.')
        messages.success(request, 'Service listing updated.')
        return redirect('staff_listings')
    return render(request, 'core/staff_listing_edit.html', {'form': form, 'listing': listing})


@staff_permission_required('view_providerprofile')
def staff_providers(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        provider = get_object_or_404(ProviderProfile.objects.select_related('user'), pk=request.POST.get('provider_id'))
        if action in ('verify', 'unverify'):
            if not (request.user.is_superuser or request.user.has_perm('core.change_providerprofile')):
                raise PermissionDenied
            provider.verified = action == 'verify'
            provider.save(update_fields=['verified', 'updated_at'])
            log_admin_action(request, action, provider, 'Updated provider verification status.')
            messages.success(request, f'Provider "{provider.user.username}" verification was updated.')
        elif action in ('activate', 'deactivate'):
            if not request.user.is_superuser:
                raise PermissionDenied
            if provider.user.is_superuser:
                raise PermissionDenied
            provider.user.is_active = action == 'activate'
            provider.user.save(update_fields=['is_active'])
            log_admin_action(request, action, provider.user, 'Updated provider account status.')
            messages.success(request, f'Provider account "{provider.user.username}" was updated.')
        else:
            messages.error(request, 'Choose a valid provider action.')
        return redirect('staff_providers')

    providers = ProviderProfile.objects.select_related('user').annotate(
        average_rating=Avg('user__service_listings__bookings__review__rating',
                           filter=Q(user__service_listings__bookings__review__is_public=True)),
        listing_count=Count('user__service_listings', distinct=True),
    ).order_by('-created_at')
    query = request.GET.get('q', '').strip()
    verified = request.GET.get('verified', '')
    if query:
        providers = providers.filter(
            Q(user__username__icontains=query) | Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) | Q(business_name__icontains=query) |
            Q(skills__icontains=query) | Q(service_areas__icontains=query)
        )
    if verified in ('true', 'false'):
        providers = providers.filter(verified=(verified == 'true'))
    return render(request, 'core/staff_providers.html', {
        'providers': _admin_list_page(request, providers),
        'query': query,
        'verified_filter': verified,
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_providerprofile'),
        'can_manage_accounts': request.user.is_superuser,
    })


@staff_permission_required('view_profile')
def staff_customers(request):
    if request.method == 'POST':
        if not request.user.is_superuser:
            raise PermissionDenied
        customer = get_object_or_404(User, pk=request.POST.get('customer_id'), profile__role=Profile.Role.CUSTOMER)
        action = request.POST.get('action')
        if customer.is_superuser or action not in ('activate', 'deactivate'):
            raise PermissionDenied
        customer.is_active = action == 'activate'
        customer.save(update_fields=['is_active'])
        log_admin_action(request, action, customer, 'Updated customer account status.')
        messages.success(request, f'Customer account "{customer.username}" was updated.')
        return redirect('staff_customers')

    customers = User.objects.filter(profile__role=Profile.Role.CUSTOMER).annotate(
        booking_count=Count('customer_bookings'),
    ).order_by('-date_joined')
    query = request.GET.get('q', '').strip()
    if query:
        customers = customers.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) |
            Q(last_name__icontains=query) | Q(email__icontains=query)
        )
    active = request.GET.get('active', '')
    if active in ('true', 'false'):
        customers = customers.filter(is_active=(active == 'true'))
    return render(request, 'core/staff_customers.html', {
        'customers': _admin_list_page(request, customers),
        'query': query,
        'active_filter': active,
        'can_manage_accounts': request.user.is_superuser,
    })


@staff_permission_required('view_booking')
def staff_bookings(request):
    if request.method == 'POST':
        if not (request.user.is_superuser or request.user.has_perm('core.change_booking')):
            raise PermissionDenied
        booking = get_object_or_404(Booking.objects.select_related('listing__provider', 'customer'),
                                    pk=request.POST.get('booking_id'))
        valid_transitions = {
            Booking.Status.PENDING: {Booking.Status.ACCEPTED, Booking.Status.REJECTED, Booking.Status.CANCELLED},
            Booking.Status.ACCEPTED: {Booking.Status.IN_PROGRESS, Booking.Status.CANCELLED},
            Booking.Status.IN_PROGRESS: {Booking.Status.COMPLETED},
        }
        new_status = request.POST.get('status')
        if new_status not in valid_transitions.get(booking.status, set()):
            messages.error(request, 'That booking status transition is not allowed.')
        else:
            with transaction.atomic():
                previous_status = booking.status
                booking.status = new_status
                booking.save(update_fields=['status', 'updated_at'])
                BookingStatusHistory.objects.create(
                    booking=booking,
                    previous_status=previous_status,
                    new_status=new_status,
                    changed_by=request.user,
                )
                log_admin_action(request, 'status_change', booking, 'Updated booking status through the permitted workflow.')
                Notification.objects.create(
                    recipient=booking.customer,
                    message=f'Your booking status changed to {booking.get_status_display()}.',
                    link='/bookings/',
                )
            messages.success(request, f'Booking #{booking.pk} updated.')
        return redirect(request.get_full_path() if request.GET else 'staff_bookings')

    bookings = Booking.objects.select_related(
        'customer', 'listing', 'listing__provider',
    ).prefetch_related('status_history__changed_by').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    customer_id = request.GET.get('customer', '')
    provider_id = request.GET.get('provider', '')
    if query:
        bookings = bookings.filter(
            Q(customer__username__icontains=query) | Q(customer__first_name__icontains=query) |
            Q(listing__provider__username__icontains=query) | Q(listing__title__icontains=query) |
            Q(locality__icontains=query)
        )
    if status in Booking.Status.values:
        bookings = bookings.filter(status=status)
    if customer_id.isdigit():
        bookings = bookings.filter(customer_id=int(customer_id))
    if provider_id.isdigit():
        bookings = bookings.filter(listing__provider_id=int(provider_id))
    return render(request, 'core/staff_bookings.html', {
        'bookings': _admin_list_page(request, bookings),
        'query': query,
        'selected_status': status,
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_booking'),
        'statuses': Booking.Status.choices,
    })


@staff_permission_required('view_review')
def staff_reviews(request):
    if request.method == 'POST':
        if not (request.user.is_superuser or request.user.has_perm('core.change_review')):
            raise PermissionDenied
        review = get_object_or_404(Review, pk=request.POST.get('review_id'))
        action = request.POST.get('action')
        if action not in ('publish', 'hide'):
            messages.error(request, 'Choose a valid review action.')
            return redirect('staff_reviews')
        review.is_public = action == 'publish'
        review.save(update_fields=['is_public'])
        log_admin_action(request, action, review, 'Updated review visibility.')
        messages.success(request, 'Review visibility updated.')
        return redirect('staff_reviews')
    reviews = Review.objects.select_related(
        'booking__customer', 'booking__listing', 'booking__listing__provider',
    ).order_by('-created_at')
    rating = request.GET.get('rating', '')
    query = request.GET.get('q', '').strip()
    if rating.isdigit() and 1 <= int(rating) <= 5:
        reviews = reviews.filter(rating=int(rating))
    if query:
        reviews = reviews.filter(
            Q(comment__icontains=query) | Q(booking__listing__title__icontains=query) |
            Q(booking__customer__username__icontains=query)
        )
    provider_id = request.GET.get('provider', '')
    if provider_id.isdigit():
        reviews = reviews.filter(booking__listing__provider_id=int(provider_id))
    return render(request, 'core/staff_reviews.html', {
        'reviews': _admin_list_page(request, reviews),
        'query': query,
        'selected_rating': rating,
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_review'),
    })


@staff_permission_required('view_complaint')
def staff_complaints(request):
    if request.method == 'POST':
        if not (request.user.is_superuser or request.user.has_perm('core.change_complaint')):
            raise PermissionDenied
        complaint = get_object_or_404(Complaint, pk=request.POST.get('complaint_id'))
        status = request.POST.get('status')
        if status not in Complaint.Status.values:
            messages.error(request, 'Choose a valid complaint status.')
        else:
            form = ComplaintAdminForm(request.POST, instance=complaint)
            if not form.is_valid():
                messages.error(request, 'The complaint update was invalid.')
                return redirect('staff_complaints')
            form.save()
            log_admin_action(request, 'resolve' if status == Complaint.Status.RESOLVED else 'update',
                             complaint, 'Updated complaint status and resolution notes.')
            messages.success(request, f'Complaint #{complaint.pk} status updated.')
        return redirect('staff_complaints')
    complaints = Complaint.objects.select_related('submitted_by', 'booking').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if query:
        complaints = complaints.filter(
            Q(subject__icontains=query) | Q(message__icontains=query) |
            Q(submitted_by__username__icontains=query)
        )
    if status in Complaint.Status.values:
        complaints = complaints.filter(status=status)
    return render(request, 'core/staff_complaints.html', {
        'complaints': _admin_list_page(request, complaints),
        'query': query,
        'selected_status': status,
        'statuses': Complaint.Status.choices,
        'can_change': request.user.is_superuser or request.user.has_perm('core.change_complaint'),
    })


@staff_permission_required('view_findora_dashboard')
def staff_dashboard(request):
    today = timezone.localdate()
    start_date = today - timedelta(days=13)
    booking_counts = {
        item['day']: item['count']
        for item in Booking.objects.filter(created_at__date__gte=start_date, created_at__date__lte=today)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
    }
    daily_bookings = [
        {'day': start_date + timedelta(days=offset), 'count': booking_counts.get(start_date + timedelta(days=offset), 0)}
        for offset in range(14)
    ]
    max_daily_bookings = max((item['count'] for item in daily_bookings), default=0)
    booking_statuses = [
        {
            'value': status.value,
            'label': status.label,
            'count': Booking.objects.filter(status=status.value).count(),
        }
        for status in Booking.Status
    ]
    can_view_customers = request.user.is_superuser or request.user.has_perm('core.view_profile')
    can_view_providers = request.user.is_superuser or request.user.has_perm('core.view_providerprofile')
    can_view_listings = request.user.is_superuser or request.user.has_perm('core.view_servicelisting')
    can_view_bookings = request.user.is_superuser or request.user.has_perm('core.view_booking')
    can_view_reviews = request.user.is_superuser or request.user.has_perm('core.view_review')
    can_view_complaints = request.user.is_superuser or request.user.has_perm('core.view_complaint')
    can_view_categories = request.user.is_superuser or request.user.has_perm('core.view_category')
    popular_categories = Category.objects.annotate(
        booking_count=Count('listings__bookings'),
    ).order_by('-booking_count', 'name')[:5]
    context = {
        'customer_count': Profile.objects.filter(role=Profile.Role.CUSTOMER).count(),
        'provider_count': ProviderProfile.objects.count(),
        'active_provider_count': ProviderProfile.objects.filter(user__is_active=True).count(),
        'verified_provider_count': ProviderProfile.objects.filter(verified=True, user__is_active=True).count(),
        'pending_provider_count': ProviderProfile.objects.filter(verified=False).count(),
        'booking_count': Booking.objects.count(),
        'pending_booking_count': Booking.objects.filter(status=Booking.Status.PENDING).count(),
        'active_booking_count': Booking.objects.filter(
            status__in=[Booking.Status.ACCEPTED, Booking.Status.IN_PROGRESS],
        ).count(),
        'completed_count': Booking.objects.filter(status=Booking.Status.COMPLETED).count(),
        'cancelled_count': Booking.objects.filter(status=Booking.Status.CANCELLED).count(),
        'listing_count': ServiceListing.objects.count(),
        'category_count': Category.objects.count(),
        'review_count': Review.objects.count(),
        'complaint_count': Complaint.objects.exclude(status=Complaint.Status.RESOLVED).count(),
        'average_rating': Review.objects.filter(is_public=True).aggregate(value=Avg('rating'))['value'],
        'employee_count': TeamAdminAccount.objects.filter(user__is_active=True).count() if request.user.is_superuser else None,
        'booking_statuses': booking_statuses,
        'daily_bookings': daily_bookings,
        'max_daily_bookings': max_daily_bookings,
        'popular_categories': popular_categories,
        'pending_providers': ProviderProfile.objects.filter(verified=False).select_related('user')
            .order_by('created_at')[:5] if can_view_providers else [],
        'recent_bookings': Booking.objects.select_related('customer', 'listing', 'listing__provider')
            .order_by('-created_at')[:6] if can_view_bookings else [],
        'open_complaints': Complaint.objects.exclude(status=Complaint.Status.RESOLVED)
            .select_related('submitted_by').order_by('-created_at')[:5] if can_view_complaints else [],
        'recent_reviews': Review.objects.filter(is_public=True)
            .select_related('booking', 'booking__customer', 'booking__listing')
            .order_by('-created_at')[:5] if can_view_reviews else [],
        'can_view_customers': can_view_customers,
        'can_view_providers': can_view_providers,
        'can_view_listings': can_view_listings,
        'can_view_bookings': can_view_bookings,
        'can_view_reviews': can_view_reviews,
        'can_view_complaints': can_view_complaints,
        'can_view_categories': can_view_categories,
        'recent_admin_actions': AdminAuditLog.objects.select_related('actor').order_by('-created_at')[:8]
        if request.user.is_superuser else [],
    }
    return render(request, 'core/staff_dashboard.html', context)


@primary_admin_required
def team_admins(request):
    form = TeamAdminCreateForm(request.POST or None)
    form.fields['permissions'].initial = form.fields['permissions'].queryset.filter(
        codename='view_findora_dashboard',
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            teammate = form.save(commit=False)
            teammate.is_staff = True
            teammate.is_superuser = False
            teammate.save()
            teammate.groups.clear()
            teammate.user_permissions.set(form.cleaned_data['permissions'])
            account = TeamAdminAccount.objects.create(user=teammate, created_by=request.user)
            log_admin_action(request, 'create', account, 'Created employee account and assigned permissions.')
        messages.success(request, f'Administrator account "{teammate.username}" created. They must change the initial password when they sign in.')
        return redirect('team_admins')
    return render(request, 'core/team_admins.html', {
        'form': form,
        'teammates': TeamAdminAccount.objects.select_related('user').prefetch_related('user__user_permissions')
            .order_by('user__username'),
        'available_permissions': team_permission_queryset(),
    })


@primary_admin_required
@require_POST
def team_admin_update(request, user_id):
    account = get_object_or_404(
        TeamAdminAccount.objects.select_related('user').exclude(user__is_superuser=True),
        user_id=user_id,
    )
    form = TeamAdminUpdateForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            account.user.is_active = form.cleaned_data['is_active']
            account.user.save(update_fields=['is_active'])
            account.user.groups.clear()
            account.user.user_permissions.set(form.cleaned_data['permissions'])
            log_admin_action(request, 'update', account, 'Updated employee account access and permissions.')
        messages.success(request, f'Administrator account "{account.user.username}" was updated.')
    else:
        messages.error(request, 'The account settings were invalid. No changes were saved.')
    return redirect('team_admins')


@primary_admin_required
def team_admin_reset_password(request, user_id):
    account = get_object_or_404(
        TeamAdminAccount.objects.select_related('user').exclude(user__is_superuser=True),
        user_id=user_id,
    )
    form = TeamAdminPasswordResetForm(account.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            account.must_change_password = True
            account.save(update_fields=['must_change_password', 'updated_at'])
            log_admin_action(request, 'password_reset', account, 'Reset employee password; change required at next sign-in.')
        messages.success(request, f'A new password was set for "{account.user.username}". The teammate must change it at next sign-in.')
        return redirect('team_admins')
    return render(request, 'core/staff_form_page.html', {
        'form': form,
        'title': f'Reset password for {account.user.username}',
        'submit_label': 'Set temporary password',
    })


@login_required(login_url='staff_login')
def team_admin_password_change(request):
    account = TeamAdminAccount.objects.filter(user=request.user).first()
    if account is None and not request.user.is_superuser:
        raise Http404
    form = TeamAdminPasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            if account:
                account.must_change_password = False
                account.save(update_fields=['must_change_password', 'updated_at'])
        update_session_auth_hash(request, user)
        if account:
            log_admin_action(request, 'password_change', account, 'Employee changed their password.')
        messages.success(request, 'Your password has been changed.')
        return redirect(admin_landing_url(request.user))
    return render(request, 'core/staff_form_page.html', {
        'form': form,
        'title': 'Change your administrator password',
        'submit_label': 'Update password',
    })

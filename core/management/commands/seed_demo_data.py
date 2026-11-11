from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Booking,
    BookingStatusHistory,
    Category,
    Complaint,
    Notification,
    Profile,
    ProviderProfile,
    Review,
    ServiceListing,
)


DEMO_PASSWORD = 'Findora-Demo-2026!'

CUSTOMER_NAMES = (
    ('Avery', 'Demo'), ('Jordan', 'Sample'), ('Taylor', 'Fiction'),
    ('Morgan', 'Example'), ('Riley', 'Demo'), ('Casey', 'Sample'),
    ('Quinn', 'Fiction'), ('Parker', 'Example'), ('Rowan', 'Demo'),
    ('Skyler', 'Sample'), ('Reese', 'Fiction'), ('Cameron', 'Example'),
    ('Finley', 'Demo'), ('Emerson', 'Sample'), ('Sage', 'Fiction'),
    ('Dakota', 'Example'), ('Alex', 'Demo'), ('Jamie', 'Sample'),
    ('Robin', 'Fiction'), ('Kendall', 'Example'),
)

PROVIDER_DATA = (
    ('Arden', 'Vale', 'Electrician', 'Wiring, lighting, outlet repair', 8, 'Maple Quarter', 95),
    ('Blair', 'North', 'Plumber', 'Leak repair, faucets, drain clearing', 11, 'Cedar Heights', 80),
    ('Cory', 'Wells', 'Carpenter', 'Cabinet repair, shelving, trim work', 7, 'Willow District', 75),
    ('Drew', 'Harbor', 'House Cleaner', 'Deep cleaning, kitchens, move-out cleaning', 6, 'Pine Terrace', 55),
    ('Ellis', 'Stone', 'Mechanic', 'Brake checks, diagnostics, routine service', 10, 'Maple Quarter', 90),
    ('Frankie', 'Reed', 'Painter', 'Interior painting, wall preparation, touch-ups', 9, 'Cedar Heights', 70),
    ('Gray', 'Marlow', 'AC Repair', 'Seasonal servicing, filters, cooling diagnostics', 12, 'Willow District', 105),
    ('Hollis', 'Brook', 'Appliance Repair', 'Washer, refrigerator, and oven troubleshooting', 8, 'Pine Terrace', 85),
    ('Indigo', 'Park', 'Electrician', 'Safety checks, switches, lighting installation', 5, 'Willow District', 78),
    ('Jules', 'Alder', 'Plumber', 'Pipe fitting, bathroom fixtures, water pressure', 13, 'Maple Quarter', 100),
    ('Kit', 'Rowe', 'Carpenter', 'Furniture assembly, doors, custom shelves', 6, 'Cedar Heights', 68),
    ('Lane', 'Sutton', 'House Cleaner', 'Regular home care, bathrooms, floor cleaning', 4, 'Pine Terrace', 48),
)

CATEGORY_DETAILS = {
    'Electrician': ('Electrical repairs and lighting services.', Category.Icon.BOLT),
    'Plumber': ('Plumbing repairs and fixture installation.', Category.Icon.WRENCH),
    'Carpenter': ('Carpentry, furniture, and fixture repairs.', Category.Icon.WRENCH),
    'House Cleaner': ('Home cleaning and move-out services.', Category.Icon.CLEANING),
    'Mechanic': ('Vehicle inspection and maintenance services.', Category.Icon.WRENCH),
    'Painter': ('Interior painting and surface preparation.', Category.Icon.PAINTBRUSH),
    'AC Repair': ('Air conditioning maintenance and repairs.', Category.Icon.WRENCH),
    'Appliance Repair': ('Household appliance diagnostics and repair.', Category.Icon.WRENCH),
}

BOOKING_STATUSES = (
    *([Booking.Status.PENDING] * 4),
    *([Booking.Status.ACCEPTED] * 2),
    *([Booking.Status.IN_PROGRESS] * 2),
    *([Booking.Status.COMPLETED] * 25),
    *([Booking.Status.CANCELLED] * 2),
)

REVIEW_COMMENTS = (
    'Arrived on time and explained the work clearly.',
    'Careful work and a tidy finish.',
    'The repair was completed just as discussed.',
    'Friendly service and helpful advice.',
    'Everything is working well after the visit.',
    'Good communication from booking through completion.',
    'The work area was left clean and organized.',
    'A practical solution and a smooth appointment.',
    'Professional, patient, and thorough.',
    'The issue was fixed in one visit.',
    'Clear estimate and reliable service.',
    'Very considerate while working in the home.',
    'The finished work looks great.',
    'Helpful update before arriving.',
    'An easy and pleasant service experience.',
    'The appointment went according to plan.',
    'Thoughtful details and solid workmanship.',
    'Quick diagnosis and a clear explanation.',
    'The service matched the listing description.',
    'Polite, efficient, and dependable.',
    'Good care was taken around the house.',
    'A straightforward booking and quality work.',
    'The repair has held up nicely.',
    'Kept me informed and finished on schedule.',
    'A neat result and useful maintenance tips.',
)


class Command(BaseCommand):
    help = 'Create or update clearly marked Findora demonstration records.'

    def handle(self, *args, **options):
        created = {name: 0 for name in (
            'customers', 'providers', 'categories', 'listings', 'bookings',
            'reviews', 'notifications', 'complaints',
        )}
        with transaction.atomic():
            categories = self._ensure_categories(created)
            customers = self._ensure_customers(created)
            providers = self._ensure_providers(categories, created)
            bookings = self._ensure_bookings(customers, providers, created)
            self._ensure_reviews(bookings, created)
            self._ensure_notifications(customers, providers, bookings, created)
            self._ensure_complaints(customers, bookings, created)

        self.stdout.write(self.style.SUCCESS('Findora demo data is ready.'))
        self.stdout.write('Created this run: ' + ', '.join(
            f'{count} {name}' for name, count in created.items()
        ))
        self.stdout.write(
            f'Log in with any demo account and password: {DEMO_PASSWORD}'
        )

    def _ensure_categories(self, created):
        categories = {}
        for name, (description, icon) in CATEGORY_DETAILS.items():
            category, was_created = Category.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'icon': icon,
                    'is_active': True,
                    'is_demo': True,
                },
            )
            if was_created:
                created['categories'] += 1
            categories[name] = category
        return categories

    def _ensure_customers(self, created):
        customers = []
        for index, (first_name, last_name) in enumerate(CUSTOMER_NAMES, start=1):
            username = f'demo_customer{index:02d}'
            email = f'demo_customer{index:02d}@example.com'
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first_name, 'last_name': last_name},
            )
            if was_created:
                created['customers'] += 1
            self._assert_demo_user(user, email, was_created)
            user.email = email
            user.first_name = first_name
            user.last_name = f'{last_name} {index:02d} (DEMO)'
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(DEMO_PASSWORD)
            user.save()
            profile, profile_created = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'role': Profile.Role.CUSTOMER,
                    'phone': f'+1-202-555-{100 + index:04d}',
                    'locality': 'Demo District',
                    'is_demo': True,
                },
            )
            if not profile_created and not profile.is_demo:
                raise CommandError(f'Profile for {username} is not marked as demo.')
            profile.role = Profile.Role.CUSTOMER
            profile.phone = f'+1-202-555-{100 + index:04d}'
            profile.locality = 'Demo District'
            profile.is_demo = True
            profile.save()
            customers.append(user)
        return customers

    def _ensure_providers(self, categories, created):
        providers = []
        for index, (first, last, category_name, skills, experience, locality, price) in enumerate(
            PROVIDER_DATA, start=1
        ):
            username = f'demo_provider{index:02d}'
            email = f'demo_provider{index:02d}@example.com'
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first, 'last_name': last},
            )
            if was_created:
                created['providers'] += 1
            self._assert_demo_user(user, email, was_created)
            user.email = email
            user.first_name = first
            user.last_name = f'{last} (DEMO)'
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(DEMO_PASSWORD)
            user.save()
            profile, profile_created = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'role': Profile.Role.PROVIDER,
                    'phone': f'+1-202-555-{130 + index:04d}',
                    'locality': locality,
                    'is_demo': True,
                },
            )
            if not profile_created and not profile.is_demo:
                raise CommandError(f'Profile for {username} is not marked as demo.')
            profile.role = Profile.Role.PROVIDER
            profile.phone = f'+1-202-555-{130 + index:04d}'
            profile.locality = locality
            profile.is_demo = True
            profile.save()

            provider_profile, provider_created = ProviderProfile.objects.get_or_create(
                user=user,
                defaults={
                    'business_name': f'DEMO - {first} {last} {category_name} Services',
                    'bio': (
                        f'Demonstration profile only. {first} provides fictional {category_name.lower()} '
                        f'services in {locality}, with {experience} years of sample experience.'
                    ),
                    'skills': skills,
                    'experience_years': experience,
                    'service_areas': locality,
                    'availability': 'Monday-Friday, 9:00 AM-5:00 PM (demo schedule)',
                    'verified': True,
                    'is_demo': True,
                },
            )
            if not provider_created and not provider_profile.is_demo:
                raise CommandError(f'Provider profile for {username} is not marked as demo.')
            provider_profile.business_name = f'DEMO - {first} {last} {category_name} Services'
            provider_profile.bio = (
                f'Demonstration profile only. {first} provides fictional {category_name.lower()} '
                f'services in {locality}, with {experience} years of sample experience.'
            )
            provider_profile.skills = skills
            provider_profile.experience_years = experience
            provider_profile.service_areas = locality
            provider_profile.availability = 'Monday-Friday, 9:00 AM-5:00 PM (demo schedule)'
            provider_profile.verified = True
            provider_profile.is_demo = True
            provider_profile.save()

            title = f'DEMO - {category_name} home service {index:02d}'
            listing, listing_created = ServiceListing.objects.get_or_create(
                provider=user,
                title=title,
                defaults={
                    'category': categories[category_name],
                    'description': (
                        f'Demonstration listing for fictional {category_name.lower()} work. '
                        f'Sample skills: {skills}.'
                    ),
                    'service_area': locality,
                    'price_from': Decimal(price),
                    'is_active': True,
                    'is_demo': True,
                },
            )
            if not listing_created and not listing.is_demo:
                raise CommandError(f'Listing "{title}" is not marked as demo.')
            if listing_created:
                created['listings'] += 1
            listing.category = categories[category_name]
            listing.description = (
                f'Demonstration listing for fictional {category_name.lower()} work. '
                f'Sample skills: {skills}.'
            )
            listing.service_area = locality
            listing.price_from = Decimal(price)
            listing.is_active = True
            listing.is_demo = True
            listing.save()
            providers.append((user, listing))
        return providers

    def _ensure_bookings(self, customers, providers, created):
        today = timezone.localdate()
        bookings = []
        for index, status in enumerate(BOOKING_STATUSES, start=1):
            customer = customers[(index * 3 - 1) % len(customers)]
            provider, listing = providers[(index * 5 - 1) % len(providers)]
            preferred_date = self._booking_date(today, index, status)
            description = f'DEMO BOOKING {index:02d} - Please inspect and advise on the sample service.'
            booking = Booking.objects.filter(
                customer=customer, listing=listing, issue_description=description,
            ).first()
            if booking is not None and not booking.is_demo:
                raise CommandError(f'Booking {index:02d} already exists and is not marked as demo.')
            defaults = {
                'address': f'{20 + index} Demo Lane',
                'locality': listing.service_area,
                'preferred_date': preferred_date,
                'preferred_time': time(9 + index % 8, (index % 2) * 30),
                'status': status,
                'is_demo': True,
            }
            if booking is None:
                booking = Booking.objects.create(
                    customer=customer,
                    listing=listing,
                    issue_description=description,
                    **defaults,
                )
                created['bookings'] += 1
            else:
                for field, value in defaults.items():
                    setattr(booking, field, value)
                booking.save()
            self._ensure_booking_history(booking, provider, status)
            bookings.append(booking)
        return bookings

    @staticmethod
    def _booking_date(today, index, status):
        if status in (Booking.Status.PENDING, Booking.Status.ACCEPTED):
            return today + timedelta(days=3 + index)
        if status == Booking.Status.IN_PROGRESS:
            return today
        if status == Booking.Status.COMPLETED:
            return today - timedelta(days=2 + index * 3)
        return today - timedelta(days=index) if index % 2 else today + timedelta(days=index)

    @staticmethod
    def _ensure_booking_history(booking, provider, status):
        if status == Booking.Status.PENDING:
            return
        if status == Booking.Status.ACCEPTED:
            transitions = [(Booking.Status.PENDING, Booking.Status.ACCEPTED)]
        elif status == Booking.Status.IN_PROGRESS:
            transitions = [
                (Booking.Status.PENDING, Booking.Status.ACCEPTED),
                (Booking.Status.ACCEPTED, Booking.Status.IN_PROGRESS),
            ]
        elif status == Booking.Status.COMPLETED:
            transitions = [
                (Booking.Status.PENDING, Booking.Status.ACCEPTED),
                (Booking.Status.ACCEPTED, Booking.Status.IN_PROGRESS),
                (Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED),
            ]
        else:
            transitions = [(Booking.Status.PENDING, Booking.Status.CANCELLED)]
        for previous_status, new_status in transitions:
            history = BookingStatusHistory.objects.filter(
                booking=booking,
                previous_status=previous_status,
                new_status=new_status,
            ).first()
            if history is not None and not history.is_demo:
                raise CommandError(
                    f'Booking history for demo booking {booking.pk} contains an unmarked record.'
                )
            if history is None:
                BookingStatusHistory.objects.create(
                    booking=booking,
                    previous_status=previous_status,
                    new_status=new_status,
                    changed_by=provider,
                    is_demo=True,
                )
            else:
                history.changed_by = provider
                history.is_demo = True
                history.save(update_fields=['changed_by', 'is_demo'])

    def _ensure_reviews(self, bookings, created):
        completed = [booking for booking in bookings if booking.status == Booking.Status.COMPLETED]
        for index, (booking, comment) in enumerate(zip(completed, REVIEW_COMMENTS)):
            review, was_created = Review.objects.get_or_create(
                booking=booking,
                defaults={
                    'rating': 3 + index % 3,
                    'comment': f'DEMO: {comment}',
                    'is_public': True,
                    'is_demo': True,
                },
            )
            if not was_created and not review.is_demo:
                raise CommandError(f'Review for booking {booking.pk} is not marked as demo.')
            if was_created:
                created['reviews'] += 1
            review.rating = 3 + index % 3
            review.comment = f'DEMO: {comment}'
            review.is_public = True
            review.is_demo = True
            review.save()

    def _ensure_notifications(self, customers, providers, bookings, created):
        samples = []
        for index, booking in enumerate(bookings[:12], start=1):
            samples.append((
                booking.customer,
                f'DEMO: Your sample booking {index:02d} is {booking.get_status_display().lower()}.',
                '/bookings/',
            ))
        for index, (provider, _listing) in enumerate(providers, start=1):
            samples.append((
                provider,
                f'DEMO: Sample provider notification {index:02d}.',
                '/dashboard/',
            ))
        for index, customer in enumerate(customers[:8], start=1):
            samples.append((
                customer,
                f'DEMO: Welcome to the Findora demonstration, customer {index:02d}.',
                '/dashboard/',
            ))
        for recipient, message, link in samples:
            notification, was_created = Notification.objects.get_or_create(
                recipient=recipient,
                message=message,
                link=link,
                defaults={'is_read': False, 'is_demo': True},
            )
            if not was_created and not notification.is_demo:
                raise CommandError(f'Notification for {recipient.username} is not marked as demo.')
            if was_created:
                created['notifications'] += 1
            notification.is_read = False
            notification.is_demo = True
            notification.save()

    def _ensure_complaints(self, customers, bookings, created):
        for index, (customer, booking, status) in enumerate((
            (customers[0], bookings[0], Complaint.Status.OPEN),
            (customers[4], bookings[10], Complaint.Status.REVIEWING),
            (customers[8], bookings[20], Complaint.Status.RESOLVED),
            (customers[12], bookings[30], Complaint.Status.OPEN),
        ), start=1):
            subject = f'DEMO: Sample support request {index:02d}'
            complaint, was_created = Complaint.objects.get_or_create(
                submitted_by=customer,
                subject=subject,
                defaults={
                    'booking': booking,
                    'message': (
                        f'Demonstration complaint {index:02d}. This fictional request is included '
                        'to populate the support workflow for the faculty presentation.'
                    ),
                    'status': status,
                    'resolution_notes': 'Resolved as a demonstration record.' if status == Complaint.Status.RESOLVED else '',
                    'is_demo': True,
                },
            )
            if not was_created and not complaint.is_demo:
                raise CommandError(f'Complaint "{subject}" is not marked as demo.')
            if was_created:
                created['complaints'] += 1
            complaint.booking = booking
            complaint.status = status
            complaint.is_demo = True
            complaint.save()

    @staticmethod
    def _assert_demo_user(user, expected_email, was_created):
        if user.email != expected_email or (
            not was_created and (not hasattr(user, 'profile') or not user.profile.is_demo)
        ):
            raise CommandError(
                f'Username "{user.username}" is already in use by a non-demo account; '
                'no data was changed.'
            )

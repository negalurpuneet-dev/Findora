from datetime import date, time, timedelta

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Booking, BookingStatusHistory, Category, Complaint, Notification, Profile,
    ProviderProfile, Review, ServiceListing, TeamAdminAccount,
)


class FindoraWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username='customer', password='Strong-test-pass-91')
        Profile.objects.create(user=self.customer, role=Profile.Role.CUSTOMER)
        self.provider = User.objects.create_user(username='provider', password='Strong-test-pass-92')
        Profile.objects.create(user=self.provider, role=Profile.Role.PROVIDER)
        ProviderProfile.objects.create(user=self.provider, business_name='Local Fixers',
                                       service_areas='Central', verified=True)
        self.other_customer = User.objects.create_user(username='other', password='Strong-test-pass-93')
        Profile.objects.create(user=self.other_customer, role=Profile.Role.CUSTOMER)
        self.category = Category.objects.create(name='Plumbing')
        self.listing = ServiceListing.objects.create(
            provider=self.provider, category=self.category, title='Pipe repair',
            description='Residential plumbing repairs', service_area='Central',
        )

    def test_registration_creates_customer_profile_without_staff_access(self):
        response = self.client.post(reverse('register'), {
            'username': 'newcustomer', 'first_name': 'New', 'email': 'new@example.com',
            'role': Profile.Role.CUSTOMER, 'password1': 'Strong-test-pass-94',
            'password2': 'Strong-test-pass-94',
        })
        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(username='newcustomer')
        self.assertEqual(user.profile.role, Profile.Role.CUSTOMER)
        self.assertFalse(user.is_staff)

    def test_public_registration_cannot_create_an_administrator(self):
        response = self.client.post(reverse('register'), {
            'username': 'publicadmin',
            'first_name': 'Public',
            'email': 'publicadmin@example.com',
            'role': 'admin',
            'password1': 'Strong-test-pass-108',
            'password2': 'Strong-test-pass-108',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='publicadmin').exists())
        self.assertContains(response, 'Select a valid choice')

    def test_listing_search_uses_verified_provider_records(self):
        response = self.client.get(reverse('service_list'), {'q': 'pipe', 'locality': 'Central'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pipe repair')
        self.assertContains(response, reverse('booking_create', args=[self.listing.pk]))

    def test_public_pages_render(self):
        home_response = self.client.get(reverse('home'))
        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, 'href="/static/core/site.css"')
        self.assertContains(home_response, 'src="/static/core/site.js"')
        self.assertContains(home_response, f'href="{reverse("staff_login")}"')
        self.assertContains(home_response, 'Staff Admin')
        self.assertContains(home_response, 'id="how-it-works"')
        self.assertContains(home_response, 'name="category"')
        self.assertEqual(self.client.get(reverse('about')).status_code, 200)
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('category_detail', args=[self.category.slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse('provider_detail', args=[self.provider.pk])).status_code, 200)

    def test_staff_login_includes_accessible_password_toggle(self):
        response = self.client.get(reverse('staff_login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'aria-label="Show password"')
        self.assertContains(response, 'Sign in to administration')

    def test_staff_profile_updates_only_the_signed_in_admin_profile(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-125',
        )
        self.client.force_login(owner)
        response = self.client.get(reverse('staff_profile'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('staff_profile'), {
            'first_name': 'Findora',
            'last_name': 'Owner',
            'email': 'admin@example.com',
            'is_superuser': '',
        })
        self.assertRedirects(response, reverse('staff_profile'))
        owner.refresh_from_db()
        self.assertEqual(owner.first_name, 'Findora')
        self.assertEqual(owner.last_name, 'Owner')
        self.assertEqual(owner.email, 'admin@example.com')
        self.assertTrue(owner.is_superuser)

    def test_private_admin_pages_render_for_superuser(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-121',
        )
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Review sample booking',
            address='Private address', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
            status=Booking.Status.COMPLETED,
        )
        Review.objects.create(booking=booking, rating=5, comment='Helpful service')
        Complaint.objects.create(
            submitted_by=self.customer, booking=booking,
            subject='A sample complaint', message='A private support request.',
        )
        employee = User.objects.create_user(
            username='employee', password='Strong-test-pass-122', is_staff=True,
        )
        TeamAdminAccount.objects.create(user=employee, created_by=owner)
        self.client.force_login(owner)

        dashboard_response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, 'aria-controls="staff-sidebar"')
        self.assertContains(dashboard_response, 'aria-label="Open administration menu"')
        self.assertContains(dashboard_response, 'aria-hidden="true"')

        paths = [
            'staff_dashboard', 'staff_categories', 'staff_listings', 'staff_providers',
            'staff_customers', 'staff_bookings', 'staff_reviews', 'staff_complaints',
            'team_admins',
        ]
        for name in paths:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('staff_listing_edit', args=[self.listing.pk])).status_code, 200,
        )

    def test_site_root_shows_home_page_for_authenticated_users(self):
        for user in (self.customer, self.provider):
            self.client.force_login(user)
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Find Local Help. Book with Confidence.')
            self.assertContains(response, 'Find services')

    def test_successful_customer_login_lands_on_role_aware_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': self.customer.username,
            'password': 'Strong-test-pass-91',
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_provider_signup_prefills_role_and_creates_provider_profile(self):
        response = self.client.get(reverse('register'), {'role': Profile.Role.PROVIDER})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="provider" selected>')
        response = self.client.post(reverse('register'), {
            'username': 'newprovider', 'first_name': 'New', 'email': 'provider@example.com',
            'role': Profile.Role.PROVIDER, 'password1': 'Strong-test-pass-95',
            'password2': 'Strong-test-pass-95',
        })
        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(username='newprovider')
        self.assertEqual(user.profile.role, Profile.Role.PROVIDER)
        self.assertTrue(ProviderProfile.objects.filter(user=user).exists())

    def test_invalid_price_filter_is_reported(self):
        response = self.client.get(reverse('service_list'), {'min_price': 'not-a-price'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Price filters must be valid')

    def test_invalid_search_filters_are_reported_instead_of_silently_ignored(self):
        response = self.client.get(reverse('service_list'), {
            'category': 'invalid', 'min_experience': '-1', 'min_rating': '8',
        })
        self.assertContains(response, 'The selected category was invalid')
        self.assertContains(response, 'Minimum experience must be a non-negative whole number')
        self.assertContains(response, 'Minimum rating must be between 1 and 5')

    def test_inconsistent_price_range_is_reported(self):
        response = self.client.get(reverse('service_list'), {'min_price': '100', 'max_price': '50'})
        self.assertContains(response, 'Minimum price cannot be higher than maximum price')

    def test_hidden_reviews_do_not_affect_public_rating(self):
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair tap',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
            status=Booking.Status.COMPLETED,
        )
        Review.objects.create(booking=booking, rating=1, is_public=False)
        response = self.client.get(reverse('service_list'))
        self.assertIsNone(response.context['page_obj'][0].avg_rating)

    def test_customer_can_request_and_track_booking(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('booking_create', args=[self.listing.pk]), {
            'issue_description': 'Kitchen tap is leaking',
            'address': '12 Example Street',
            'locality': 'Central',
            'preferred_date': (date.today() + timedelta(days=2)).isoformat(),
            'preferred_time': time(10, 30).isoformat(),
        })
        self.assertRedirects(response, reverse('booking_list'))
        booking = Booking.objects.get(customer=self.customer)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.listing.provider, self.provider)
        self.assertEqual(self.provider.notifications.count(), 1)

    def test_provider_workflow_and_completed_booking_review(self):
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair tap',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
        )
        self.client.force_login(self.provider)
        for action, expected in [
            ('accept', Booking.Status.ACCEPTED),
            ('start', Booking.Status.IN_PROGRESS),
            ('complete', Booking.Status.COMPLETED),
        ]:
            response = self.client.post(reverse('booking_transition', args=[booking.pk]), {'action': action})
            self.assertRedirects(response, reverse('booking_list'))
            booking.refresh_from_db()
            self.assertEqual(booking.status, expected)
        self.client.force_login(self.customer)
        response = self.client.post(reverse('review_create', args=[booking.pk]), {'rating': 5, 'comment': 'Great work'})
        self.assertRedirects(response, reverse('booking_list'))
        self.assertEqual(Review.objects.get(booking=booking).rating, 5)
        self.assertEqual(BookingStatusHistory.objects.filter(booking=booking).count(), 3)

    def test_unrelated_user_cannot_transition_or_view_another_customers_booking(self):
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair tap',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
        )
        self.client.force_login(self.other_customer)
        response = self.client.post(reverse('booking_transition', args=[booking.pk]), {'action': 'cancel'})
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('booking_list'))
        self.assertNotContains(response, 'Repair tap')

    def test_unverified_providers_are_not_publicly_listed(self):
        self.provider.provider_profile.verified = False
        self.provider.provider_profile.save()
        response = self.client.get(reverse('service_list'))
        self.assertNotContains(response, 'Pipe repair')

    def test_profile_and_provider_dashboard_render(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('profile_update')).status_code, 200)
        self.client.force_login(self.provider)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your services')
        self.assertContains(response, 'Recent reviews')
        self.assertContains(response, 'Active bookings')

    def test_past_booking_date_is_rejected(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('booking_create', args=[self.listing.pk]), {
            'issue_description': 'Kitchen tap is leaking',
            'address': '12 Example Street',
            'locality': 'Central',
            'preferred_date': (date.today() - timedelta(days=1)).isoformat(),
            'preferred_time': time(10, 30).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.exists())
        self.assertContains(response, 'Choose today or a future date.')

    def test_non_staff_cannot_open_admin_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_public_pages_do_not_expose_admin_urls(self):
        pages = [
            reverse('home'), reverse('about'), reverse('service_list'),
            reverse('login'), reverse('register'),
        ]
        for page in pages:
            with self.subTest(page=page):
                response = self.client.get(page)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, '/admin/')
                self.assertContains(response, f'href="{reverse("staff_login")}"')
                self.assertNotContains(response, reverse('staff_dashboard'))

        for user, page in [
            (self.customer, reverse('dashboard')),
            (self.provider, reverse('dashboard')),
            (self.customer, reverse('booking_list')),
            (self.provider, reverse('booking_list')),
        ]:
            self.client.force_login(user)
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '/admin/')
            self.assertContains(response, f'href="{reverse("staff_login")}"')
            self.assertNotContains(response, reverse('staff_dashboard'))

    def test_customer_and_provider_are_forbidden_from_admin_routes(self):
        for user in (self.customer, self.provider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('staff_login')).status_code, 403)
            for route in ('staff_dashboard', 'team_admins'):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 403)
            response = self.client.get(reverse('admin:core_booking_changelist'))
            self.assertEqual(response.status_code, 403)
            response = self.client.get(reverse('admin:login'))
            self.assertEqual(response.status_code, 403)

    def test_anonymous_staff_page_redirects_to_private_login(self):
        response = self.client.get(reverse('staff_bookings'))
        expected_url = f"{reverse('staff_login')}?next={reverse('staff_bookings')}"
        self.assertRedirects(response, expected_url)

    def test_anonymous_admin_request_uses_private_staff_login(self):
        response = self.client.get(reverse('admin:index'))
        expected_url = f"{reverse('staff_login')}?next={reverse('admin:index')}"
        self.assertRedirects(response, expected_url)

    def test_superuser_can_access_private_admin_directly(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-110',
        )
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)

    def test_staff_dashboard_shows_real_metrics_and_management_queues(self):
        staff_user = User.objects.create_user(
            username='staffadmin', password='Strong-test-pass-96', is_staff=True,
        )
        permission = Permission.objects.get(codename='view_findora_dashboard')
        staff_user.user_permissions.add(permission)
        staff_user.user_permissions.add(*Permission.objects.filter(
            codename__in=[
                'view_profile', 'view_providerprofile', 'view_booking', 'view_review',
                'view_complaint', 'view_category', 'view_servicelisting',
            ],
        ))
        pending_provider = User.objects.create_user(username='pendingprovider')
        ProviderProfile.objects.create(user=pending_provider, business_name='Awaiting Review')
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair kitchen sink',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
            status=Booking.Status.PENDING,
        )
        Complaint.objects.create(
            submitted_by=self.customer, booking=booking,
            subject='Scheduling concern', message='Please help with the appointment.',
        )
        completed_booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair bathroom tap',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=2), preferred_time=time(10),
            status=Booking.Status.COMPLETED,
        )
        Review.objects.create(booking=completed_booking, rating=4, comment='Clear and helpful service')

        self.client.force_login(staff_user)
        response = self.client.get(reverse('staff_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['customer_count'], 2)
        self.assertEqual(response.context['provider_count'], 2)
        self.assertEqual(response.context['pending_provider_count'], 1)
        self.assertEqual(response.context['booking_count'], 2)
        self.assertEqual(response.context['completed_count'], 1)
        self.assertEqual(response.context['complaint_count'], 1)
        self.assertEqual(response.context['average_rating'], 4)
        self.assertContains(response, 'Awaiting Review')
        self.assertContains(response, 'Scheduling concern')
        self.assertContains(response, reverse('staff_bookings'))
        self.assertContains(response, reverse('staff_providers'))

    def test_staff_login_is_separate_and_rejects_public_accounts(self):
        response = self.client.post(reverse('staff_login'), {
            'username': self.customer.username,
            'password': 'Strong-test-pass-91',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

        employee = User.objects.create_user(
            username='employee', password='Strong-test-pass-111', is_staff=True,
        )
        employee.user_permissions.add(Permission.objects.get(codename='view_profile'))
        response = self.client.post(reverse('staff_login'), {
            'username': employee.username,
            'password': 'Strong-test-pass-111',
            'next': 'https://example.invalid/',
        })
        self.assertRedirects(response, reverse('staff_customers'))

    def test_deactivated_employee_loses_access_and_cannot_be_reactivated_by_employee(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-119',
        )
        employee = User.objects.create_user(
            username='employee', password='Strong-test-pass-120', is_staff=True,
        )
        permission = Permission.objects.get(codename='view_profile')
        employee.user_permissions.add(permission)
        TeamAdminAccount.objects.create(user=employee, must_change_password=False)
        employee_client = Client()
        employee_client.force_login(employee)

        self.client.force_login(owner)
        response = self.client.post(reverse('team_admin_update', args=[employee.pk]), {
            'permissions': [permission.pk],
        })
        self.assertRedirects(response, reverse('team_admins'))
        employee.refresh_from_db()
        self.assertFalse(employee.is_active)
        response = employee_client.get(reverse('staff_customers'))
        self.assertRedirects(response, reverse('staff_login') + '?next=' + reverse('staff_customers'))

    def test_employee_dashboard_permission_does_not_grant_record_access(self):
        employee = User.objects.create_user(
            username='analytics', password='Strong-test-pass-112', is_staff=True,
        )
        private_customer = User.objects.create_user(
            username='private_record_user_913', password='Strong-test-pass-118',
        )
        Profile.objects.create(user=private_customer, role=Profile.Role.CUSTOMER)
        employee.user_permissions.add(Permission.objects.get(codename='view_findora_dashboard'))
        TeamAdminAccount.objects.create(user=employee, must_change_password=False)
        self.client.force_login(employee)

        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Platform overview')
        self.assertNotContains(response, private_customer.username)
        self.assertEqual(self.client.get(reverse('staff_customers')).status_code, 403)
        self.assertEqual(self.client.get(reverse('staff_bookings')).status_code, 403)

    def test_category_management_persists_changes_and_rejects_slug_collisions(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-113',
        )
        self.client.force_login(owner)
        response = self.client.post(reverse('staff_categories'), {
            'action': 'create',
            'name': 'Home Repair',
            'description': 'Repairs around the home',
            'icon': 'wrench',
            'is_active': 'on',
        })
        self.assertRedirects(response, reverse('staff_categories'))
        category = Category.objects.get(name='Home Repair')
        self.assertEqual(category.icon, 'wrench')

        response = self.client.post(reverse('staff_categories'), {
            'action': 'create',
            'name': 'Home-Repair',
            'description': 'Duplicate generated slug',
            'icon': '',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(name='Home-Repair').exists())

        response = self.client.post(reverse('staff_categories'), {
            'category_id': category.pk,
            'name': 'Home Services',
            'description': 'Updated category description',
            'icon': 'home',
            'is_active': '',
        })
        self.assertRedirects(response, reverse('staff_categories'))
        category.refresh_from_db()
        self.assertEqual(category.name, 'Home Services')
        self.assertEqual(category.icon, 'home')
        self.assertFalse(category.is_active)

    def test_listing_management_creates_and_updates_database_records(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-114',
        )
        self.client.force_login(owner)
        response = self.client.post(reverse('staff_listings'), {
            'create-title': 'Admin created service',
            'create-description': 'A service managed in the private panel.',
            'create-provider': self.provider.pk,
            'create-category': self.category.pk,
            'create-service_area': 'North District',
            'create-price_from': '45.00',
            'create-is_active': 'on',
        })
        self.assertRedirects(response, reverse('staff_listings'))
        listing = ServiceListing.objects.get(title='Admin created service')

        response = self.client.post(reverse('staff_listing_edit', args=[listing.pk]), {
            'title': 'Updated service title',
            'description': 'Updated description.',
            'provider': self.provider.pk,
            'category': self.category.pk,
            'service_area': 'Central',
            'price_from': '55.00',
            'is_active': '',
        })
        self.assertRedirects(response, reverse('staff_listings'))
        listing.refresh_from_db()
        self.assertEqual(listing.title, 'Updated service title')
        self.assertFalse(listing.is_active)

    def test_provider_verification_and_account_controls_are_authorized(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-115',
        )
        self.client.force_login(owner)
        profile = self.provider.provider_profile
        response = self.client.post(reverse('staff_providers'), {
            'provider_id': profile.pk,
            'action': 'unverify',
        })
        self.assertRedirects(response, reverse('staff_providers'))
        profile.refresh_from_db()
        self.assertFalse(profile.verified)
        self.assertTrue(self.provider.is_active)

        response = self.client.post(reverse('staff_providers'), {
            'provider_id': profile.pk,
            'action': 'deactivate',
        })
        self.assertRedirects(response, reverse('staff_providers'))
        self.provider.refresh_from_db()
        self.assertFalse(self.provider.is_active)

    def test_booking_admin_actions_enforce_workflow_and_record_history(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-116',
        )
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Fix a tap',
            address='Private address', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
        )
        self.client.force_login(owner)

        response = self.client.post(reverse('staff_bookings'), {
            'booking_id': booking.pk,
            'status': Booking.Status.COMPLETED,
        })
        self.assertRedirects(response, reverse('staff_bookings'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertFalse(booking.status_history.exists())

        self.client.post(reverse('staff_bookings'), {
            'booking_id': booking.pk,
            'status': Booking.Status.ACCEPTED,
        })
        booking.refresh_from_db()
        history = booking.status_history.get()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)
        self.assertEqual(history.previous_status, Booking.Status.PENDING)
        self.assertEqual(history.new_status, Booking.Status.ACCEPTED)
        self.assertEqual(history.changed_by, owner)
        audit = owner.findora_admin_actions.get(object_type='core.booking', object_id=str(booking.pk))
        self.assertIn('status', audit.summary.lower())
        self.assertNotIn('Private address', audit.summary)

    def test_review_moderation_and_complaint_resolution_are_saved(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-117',
        )
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Completed repair',
            address='Private address', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
            status=Booking.Status.COMPLETED,
        )
        review = Review.objects.create(booking=booking, rating=1, comment='Inappropriate text')
        complaint = Complaint.objects.create(
            submitted_by=self.customer, booking=booking, subject='Follow-up needed', message='Please review.',
        )
        self.client.force_login(owner)

        self.client.post(reverse('staff_reviews'), {'review_id': review.pk, 'action': 'hide'})
        review.refresh_from_db()
        self.assertFalse(review.is_public)

        self.client.post(reverse('staff_complaints'), {
            'complaint_id': complaint.pk,
            'status': Complaint.Status.RESOLVED,
            'resolution_notes': 'Reviewed and addressed with the provider.',
        })
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.RESOLVED)
        self.assertEqual(complaint.resolution_notes, 'Reviewed and addressed with the provider.')

    def test_non_superuser_staff_requires_dashboard_permission(self):
        staff_user = User.objects.create_user(
            username='unprivilegedstaff', password='Strong-test-pass-97', is_staff=True,
        )
        self.client.force_login(staff_user)
        self.assertEqual(self.client.get(reverse('staff_dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('team_admins')).status_code, 403)
        self.assertEqual(self.client.get(reverse('booking_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('complaint_create')).status_code, 403)
        self.assertEqual(
            self.client.post(reverse('team_admin_update', args=[self.customer.pk])).status_code, 403,
        )
        self.assertEqual(
            self.client.post(reverse('team_admin_reset_password', args=[self.customer.pk])).status_code, 403,
        )

    def test_team_booking_access_requires_model_permission(self):
        teammate = User.objects.create_user(
            username='bookingviewer', password='Strong-test-pass-109', is_staff=True,
        )
        dashboard_permission = Permission.objects.get(codename='view_findora_dashboard')
        teammate.user_permissions.add(dashboard_permission)
        TeamAdminAccount.objects.create(user=teammate, must_change_password=False)
        self.client.force_login(teammate)
        self.assertEqual(self.client.get(reverse('booking_list')).status_code, 403)

        booking_permission = Permission.objects.get(codename='view_booking')
        teammate.user_permissions.add(booking_permission)
        self.assertEqual(self.client.get(reverse('booking_list')).status_code, 200)

    def test_owner_can_create_a_limited_team_administrator(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-98',
        )
        permission = Permission.objects.get(codename='view_findora_dashboard')
        self.client.force_login(owner)
        response = self.client.post(reverse('team_admins'), {
            'username': 'teammate',
            'email': 'teammate@example.com',
            'password1': 'Strong-test-pass-99',
            'password2': 'Strong-test-pass-99',
            'permissions': [permission.pk],
        })
        self.assertRedirects(response, reverse('team_admins'))

        teammate = User.objects.get(username='teammate')
        self.assertTrue(teammate.is_staff)
        self.assertFalse(teammate.is_superuser)
        self.assertTrue(teammate.check_password('Strong-test-pass-99'))
        self.assertNotEqual(teammate.password, 'Strong-test-pass-99')
        self.assertEqual(list(teammate.user_permissions.all()), [permission])
        self.assertFalse(teammate.user_permissions.filter(codename__startswith='delete_').exists())
        self.assertFalse(teammate.user_permissions.filter(codename='add_booking').exists())
        self.assertTrue(teammate.team_admin_account.must_change_password)
        self.assertEqual(teammate.team_admin_account.created_by, owner)

    def test_team_admin_must_change_password_before_accessing_admin_pages(self):
        permission = Permission.objects.get(codename='view_findora_dashboard')
        teammate = User.objects.create_user(
            username='teammate', password='Strong-test-pass-100', is_staff=True,
        )
        teammate.user_permissions.add(permission)
        account = TeamAdminAccount.objects.create(user=teammate)
        self.client.force_login(teammate)

        response = self.client.get(reverse('staff_dashboard'))
        self.assertRedirects(response, reverse('team_admin_password_change'))
        response = self.client.post(reverse('team_admin_password_change'), {
            'old_password': 'Strong-test-pass-100',
            'new_password1': 'Strong-test-pass-101',
            'new_password2': 'Strong-test-pass-101',
        })
        self.assertRedirects(response, reverse('staff_dashboard'))
        account.refresh_from_db()
        teammate.refresh_from_db()
        self.assertFalse(account.must_change_password)
        self.assertTrue(teammate.check_password('Strong-test-pass-101'))
        self.assertEqual(self.client.get(reverse('staff_dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 403)

    def test_owner_can_reset_teammate_password_and_force_change(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-102',
        )
        teammate = User.objects.create_user(
            username='teammate', password='Strong-test-pass-103', is_staff=True,
        )
        account = TeamAdminAccount.objects.create(user=teammate, must_change_password=False)
        self.client.force_login(owner)

        response = self.client.post(reverse('team_admin_reset_password', args=[teammate.pk]), {
            'new_password1': 'Strong-test-pass-104',
            'new_password2': 'Strong-test-pass-104',
        })
        self.assertRedirects(response, reverse('team_admins'))
        account.refresh_from_db()
        teammate.refresh_from_db()
        self.assertTrue(account.must_change_password)
        self.assertTrue(teammate.check_password('Strong-test-pass-104'))

    def test_team_permissions_cannot_be_escalated_outside_findora_models(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-105',
        )
        teammate = User.objects.create_user(
            username='teammate', password='Strong-test-pass-106', is_staff=True,
        )
        account = TeamAdminAccount.objects.create(user=teammate)
        group = Group.objects.create(name='Unexpected elevated group')
        teammate.groups.add(group)
        user_content_type = ContentType.objects.get_for_model(User)
        user_permission = Permission.objects.create(
            codename='test_manage_users', name='Can test manage users', content_type=user_content_type,
        )

        self.client.force_login(owner)
        response = self.client.post(reverse('team_admin_update', args=[teammate.pk]), {
            'is_active': 'on',
            'permissions': [user_permission.pk],
        })
        self.assertRedirects(response, reverse('team_admins'))
        self.assertFalse(teammate.user_permissions.filter(pk=user_permission.pk).exists())
        self.assertTrue(teammate.groups.filter(pk=group.pk).exists())

        dashboard_permission = Permission.objects.get(codename='view_findora_dashboard')
        response = self.client.post(reverse('team_admin_update', args=[teammate.pk]), {
            'is_active': 'on',
            'permissions': [dashboard_permission.pk],
        })
        self.assertRedirects(response, reverse('team_admins'))
        self.assertFalse(teammate.groups.exists())
        self.assertTrue(account.user.is_active)

        self.client.post(reverse('team_admin_update', args=[teammate.pk]), {
            'permissions': [],
        })
        account.user.refresh_from_db()
        self.assertFalse(account.user.is_active)
        self.assertFalse(account.user.user_permissions.exists())

        self.client.post(reverse('team_admin_update', args=[teammate.pk]), {
            'is_active': 'on',
            'permissions': [dashboard_permission.pk],
        })
        account.user.refresh_from_db()
        self.assertTrue(account.user.is_active)

    def test_team_management_cannot_target_superuser_accounts(self):
        owner = User.objects.create_superuser(
            username='owner', email='owner@example.com', password='Strong-test-pass-107',
        )
        TeamAdminAccount.objects.create(user=owner)
        self.client.force_login(owner)
        self.assertEqual(
            self.client.post(reverse('team_admin_update', args=[owner.pk])).status_code, 404,
        )
        self.assertEqual(
            self.client.post(reverse('team_admin_reset_password', args=[owner.pk])).status_code, 404,
        )

    def test_customer_cannot_review_an_incomplete_booking(self):
        booking = Booking.objects.create(
            customer=self.customer, listing=self.listing, issue_description='Repair tap',
            address='12 Example Street', locality='Central',
            preferred_date=date.today() + timedelta(days=1), preferred_time=time(9),
        )
        self.client.force_login(self.customer)
        response = self.client.get(reverse('review_create', args=[booking.pk]))
        self.assertEqual(response.status_code, 404)

    def test_provider_cannot_submit_customer_booking_request(self):
        self.client.force_login(self.provider)
        response = self.client.get(reverse('booking_create', args=[self.listing.pk]))
        self.assertEqual(response.status_code, 404)

    def test_provider_can_edit_only_their_own_listing(self):
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(reverse('listing_update', args=[self.listing.pk])).status_code, 200)
        self.client.force_login(self.other_customer)
        self.assertEqual(self.client.get(reverse('listing_update', args=[self.listing.pk])).status_code, 404)

    def test_notifications_are_only_marked_read_by_post_action(self):
        notification = Notification.objects.create(recipient=self.customer, message='Your booking was accepted.')
        self.client.force_login(self.customer)
        self.client.get(reverse('notifications'))
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        response = self.client.post(reverse('mark_notifications_read'))
        self.assertRedirects(response, reverse('notifications'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

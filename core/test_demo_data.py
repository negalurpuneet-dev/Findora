from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase

from .models import (
    Booking,
    Category,
    Complaint,
    Notification,
    Profile,
    ProviderProfile,
    Review,
    ServiceListing,
)


class DemoDataCommandTests(TestCase):
    def test_seed_is_idempotent_and_creates_expected_related_records(self):
        call_command('seed_demo_data', stdout=StringIO())
        call_command('seed_demo_data', stdout=StringIO())

        self.assertEqual(Profile.objects.filter(is_demo=True, role=Profile.Role.CUSTOMER).count(), 20)
        self.assertEqual(Profile.objects.filter(is_demo=True, role=Profile.Role.PROVIDER).count(), 12)
        self.assertEqual(ProviderProfile.objects.filter(is_demo=True, verified=True).count(), 12)
        self.assertEqual(ServiceListing.objects.filter(is_demo=True).count(), 12)
        self.assertEqual(Booking.objects.filter(is_demo=True).count(), 35)
        self.assertEqual(Booking.objects.filter(is_demo=True, status=Booking.Status.PENDING).count(), 4)
        self.assertEqual(Booking.objects.filter(is_demo=True, status=Booking.Status.ACCEPTED).count(), 2)
        self.assertEqual(Booking.objects.filter(is_demo=True, status=Booking.Status.IN_PROGRESS).count(), 2)
        self.assertEqual(Booking.objects.filter(is_demo=True, status=Booking.Status.COMPLETED).count(), 25)
        self.assertEqual(Booking.objects.filter(is_demo=True, status=Booking.Status.CANCELLED).count(), 2)
        self.assertEqual(Review.objects.filter(is_demo=True).count(), 25)
        self.assertFalse(Review.objects.filter(is_demo=True).exclude(
            booking__status=Booking.Status.COMPLETED,
        ).exists())
        self.assertEqual(Notification.objects.filter(is_demo=True).count(), 32)
        self.assertEqual(Complaint.objects.filter(is_demo=True).count(), 4)

        customer = User.objects.get(username='demo_customer01')
        self.assertTrue(customer.check_password('Findora-Demo-2026!'))
        self.assertFalse(customer.is_staff)
        self.assertTrue(customer.profile.is_demo)

    def test_seed_refuses_to_change_reserved_real_usernames(self):
        existing = User.objects.create_user(
            username='demo_customer01',
            email='private@example.com',
            password='Original-Password-123!',
        )
        old_password = existing.password

        with self.assertRaises(CommandError):
            call_command('seed_demo_data', stdout=StringIO())

        existing.refresh_from_db()
        self.assertEqual(existing.email, 'private@example.com')
        self.assertEqual(existing.password, old_password)

    def test_cleanup_removes_only_marked_data_and_preserves_unrelated_users(self):
        call_command('seed_demo_data', stdout=StringIO())
        unrelated = User.objects.create_user(
            username='real_customer',
            email='real@example.com',
            password='Original-Password-124!',
        )
        Profile.objects.create(user=unrelated, role=Profile.Role.CUSTOMER)
        category = Category.objects.create(name='Unrelated Category')
        ServiceListing.objects.create(
            provider=unrelated,
            category=category,
            title='Unrelated listing',
            description='A real listing.',
            service_area='Real District',
        )

        call_command('remove_demo_data', stdout=StringIO())

        self.assertFalse(Profile.objects.filter(is_demo=True).exists())
        self.assertFalse(ProviderProfile.objects.filter(is_demo=True).exists())
        self.assertFalse(ServiceListing.objects.filter(is_demo=True).exists())
        self.assertFalse(Booking.objects.filter(is_demo=True).exists())
        self.assertFalse(Review.objects.filter(is_demo=True).exists())
        self.assertFalse(Notification.objects.filter(is_demo=True).exists())
        self.assertFalse(Complaint.objects.filter(is_demo=True).exists())
        self.assertTrue(User.objects.filter(pk=unrelated.pk).exists())
        self.assertTrue(ServiceListing.objects.filter(title='Unrelated listing').exists())

    def test_cleanup_stops_before_removing_related_non_demo_records(self):
        call_command('seed_demo_data', stdout=StringIO())
        demo_customer = User.objects.get(username='demo_customer01')
        Notification.objects.create(
            recipient=demo_customer,
            message='A real record that must be preserved.',
        )

        with self.assertRaises(CommandError):
            call_command('remove_demo_data', stdout=StringIO())

        self.assertTrue(User.objects.filter(pk=demo_customer.pk).exists())
        self.assertTrue(Notification.objects.filter(
            recipient=demo_customer,
            message='A real record that must be preserved.',
        ).exists())

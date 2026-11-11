from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

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


class Command(BaseCommand):
    help = 'Remove only explicitly marked Findora demonstration records.'

    def handle(self, *args, **options):
        demo_user_ids = list(Profile.objects.filter(is_demo=True).values_list('user_id', flat=True))
        demo_listing_ids = list(ServiceListing.objects.filter(is_demo=True).values_list('pk', flat=True))
        demo_booking_ids = list(Booking.objects.filter(is_demo=True).values_list('pk', flat=True))
        blockers = []
        if ServiceListing.objects.filter(provider_id__in=demo_user_ids, is_demo=False).exists():
            blockers.append('non-demo service listings owned by demo accounts')
        if Booking.objects.filter(
            Q(customer_id__in=demo_user_ids) | Q(listing_id__in=demo_listing_ids),
            is_demo=False,
        ).exists():
            blockers.append('non-demo bookings involving demo accounts or listings')
        if Review.objects.filter(booking_id__in=demo_booking_ids, is_demo=False).exists():
            blockers.append('non-demo reviews attached to demo bookings')
        if BookingStatusHistory.objects.filter(booking_id__in=demo_booking_ids, is_demo=False).exists():
            blockers.append('non-demo booking history attached to demo bookings')
        if Complaint.objects.filter(
            Q(submitted_by_id__in=demo_user_ids) | Q(booking_id__in=demo_booking_ids),
            is_demo=False,
        ).exists():
            blockers.append('non-demo complaints involving demo accounts or bookings')
        if Notification.objects.filter(recipient_id__in=demo_user_ids, is_demo=False).exists():
            blockers.append('non-demo notifications addressed to demo accounts')
        if ProviderProfile.objects.filter(user_id__in=demo_user_ids, is_demo=False).exists():
            blockers.append('non-demo provider profiles on demo accounts')
        if blockers:
            raise CommandError(
                'Cleanup stopped to protect related non-demo data: ' + '; '.join(blockers)
            )

        with transaction.atomic():
            deleted = {}
            for model in (
                Review, BookingStatusHistory, Complaint, Notification, Booking,
                ServiceListing, ProviderProfile, Profile,
            ):
                count, _details = model.objects.filter(is_demo=True).delete()
                deleted[model._meta.verbose_name_plural] = count
            User.objects.filter(pk__in=demo_user_ids).delete()
            deleted['demo accounts'] = len(demo_user_ids)
            unused_categories = Category.objects.filter(is_demo=True, listings__isnull=True)
            deleted['unused demo categories'] = unused_categories.count()
            unused_categories.delete()

        self.stdout.write(self.style.SUCCESS('Marked demo records were removed safely.'))
        self.stdout.write('Deleted: ' + ', '.join(
            f'{count} {name}' for name, count in deleted.items()
        ))

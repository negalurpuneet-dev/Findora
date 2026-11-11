from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


class Profile(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        PROVIDER = 'provider', 'Service provider'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=30, blank=True)
    locality = models.CharField(max_length=120, blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [('view_findora_dashboard', 'Can view Findora administration dashboard')]

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'


class TeamAdminAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_admin_account')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_team_admin_accounts',
    )
    must_change_password = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']
        verbose_name = 'team administrator account'
        verbose_name_plural = 'team administrator accounts'

    def __str__(self):
        return self.user.get_username()


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='findora_admin_actions',
    )
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    summary = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'administration audit entry'
        verbose_name_plural = 'administration audit entries'

    def __str__(self):
        return f'{self.action}: {self.object_type} #{self.object_id}'


class ProviderProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider_profile')
    business_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    skills = models.CharField(max_length=255, blank=True)
    experience_years = models.PositiveSmallIntegerField(default=0)
    service_areas = models.CharField(max_length=255, blank=True)
    availability = models.CharField(max_length=255, blank=True)
    verified = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business_name or self.user.get_full_name() or self.user.username


class Category(models.Model):
    class Icon(models.TextChoices):
        WRENCH = 'wrench', 'Wrench'
        HOME = 'home', 'Home'
        CLEANING = 'cleaning', 'Cleaning'
        PAINTBRUSH = 'paintbrush', 'Painting'
        BOLT = 'bolt', 'Electrical'

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.CharField(max_length=240, blank=True)
    icon = models.CharField(
        max_length=30,
        choices=Icon.choices,
        blank=True,
        help_text='Optional Findora icon identifier.',
    )
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ServiceListing(models.Model):
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='service_listings')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='listings')
    title = models.CharField(max_length=120)
    description = models.TextField()
    service_area = models.CharField(max_length=120)
    price_from = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        indexes = [models.Index(fields=['category', 'service_area', 'is_active'])]

    def __str__(self):
        return self.title


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        IN_PROGRESS = 'in_progress', 'In progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='customer_bookings')
    listing = models.ForeignKey(ServiceListing, on_delete=models.PROTECT, related_name='bookings')
    issue_description = models.TextField()
    address = models.CharField(max_length=255)
    locality = models.CharField(max_length=120)
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'preferred_date'])]

    def __str__(self):
        return f'{self.listing.title} for {self.customer.username}'


class BookingStatusHistory(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='status_history')
    previous_status = models.CharField(max_length=12, choices=Booking.Status.choices)
    new_status = models.CharField(max_length=12, choices=Booking.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking_status_changes',
    )
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.rating}/5 - booking {self.booking_id}'


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Notification for {self.recipient.username}'


class Complaint(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        REVIEWING = 'reviewing', 'Reviewing'
        RESOLVED = 'resolved', 'Resolved'

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    subject = models.CharField(max_length=120)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution_notes = models.TextField(blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject

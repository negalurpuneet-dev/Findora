from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    AdminAuditLog, Booking, BookingStatusHistory, Category, Complaint, Notification,
    Profile, ProviderProfile, Review, ServiceListing,
)

admin.site.site_header = 'Findora administration'
admin.site.site_title = 'Findora admin'
admin.site.index_title = 'Manage the Findora platform'


class AuditedModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AdminAuditLog.objects.create(
            actor=request.user,
            action='update' if change else 'create',
            object_type=obj._meta.label_lower,
            object_id=str(obj.pk),
            summary='Saved record through Django administration.',
        )


class OwnerOnlyUserAdmin(UserAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.unregister(User)
admin.site.register(User, OwnerOnlyUserAdmin)


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'object_type', 'object_id', 'summary')
    list_filter = ('action', 'object_type', 'created_at')
    search_fields = ('actor__username', 'object_type', 'object_id', 'summary')
    readonly_fields = ('actor', 'action', 'object_type', 'object_id', 'summary', 'created_at')

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(AuditedModelAdmin):
    list_display = ('name', 'icon', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ProviderProfile)
class ProviderProfileAdmin(AuditedModelAdmin):
    list_display = ('user', 'business_name', 'experience_years', 'verified')
    list_filter = ('verified',)
    search_fields = ('user__username', 'business_name', 'service_areas')
    actions = ('verify_providers',)

    @admin.action(description='Verify selected providers')
    def verify_providers(self, request, queryset):
        for provider in queryset:
            provider.verified = True
            provider.save(update_fields=('verified', 'updated_at'))
            AdminAuditLog.objects.create(
                actor=request.user,
                action='verify',
                object_type=provider._meta.label_lower,
                object_id=str(provider.pk),
                summary='Verified provider through Django administration.',
            )


@admin.register(Profile)
class ProfileAdmin(AuditedModelAdmin):
    list_display = ('user', 'role', 'phone', 'locality')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')


@admin.register(ServiceListing)
class ServiceListingAdmin(AuditedModelAdmin):
    list_display = ('title', 'provider', 'category', 'service_area', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'provider__username', 'service_area')


@admin.register(Booking)
class BookingAdmin(AuditedModelAdmin):
    list_display = ('id', 'listing', 'customer', 'status', 'preferred_date', 'created_at')
    list_filter = ('status', 'preferred_date')
    search_fields = ('customer__username', 'listing__title', 'locality')
    readonly_fields = ('status', 'created_at', 'updated_at')

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('booking', 'previous_status', 'new_status', 'changed_by', 'created_at')
    list_filter = ('previous_status', 'new_status', 'created_at')
    search_fields = ('booking__customer__username', 'booking__listing__title')
    readonly_fields = ('booking', 'previous_status', 'new_status', 'changed_by', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(AuditedModelAdmin):
    list_display = ('booking', 'rating', 'is_public', 'created_at')
    list_filter = ('rating', 'is_public')
    actions = ('hide_reviews',)

    @admin.action(description='Hide selected reviews')
    def hide_reviews(self, request, queryset):
        for review in queryset:
            review.is_public = False
            review.save(update_fields=('is_public',))
            AdminAuditLog.objects.create(
                actor=request.user,
                action='hide',
                object_type=review._meta.label_lower,
                object_id=str(review.pk),
                summary='Hid review through Django administration.',
            )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Complaint)
class ComplaintAdmin(AuditedModelAdmin):
    list_display = ('subject', 'submitted_by', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('subject', 'submitted_by__username', 'message')

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .models import Booking, Category, Complaint, Profile, ProviderProfile, Review, ServiceListing


TEAM_PERMISSION_MODELS = (
    'profile', 'providerprofile', 'category', 'servicelisting',
    'booking', 'review', 'complaint', 'notification',
)


def team_permission_queryset():
    return Permission.objects.filter(
        content_type__app_label='core',
        content_type__model__in=TEAM_PERMISSION_MODELS,
    ).filter(
        Q(codename__startswith='view_') |
        Q(codename__startswith='add_') |
        Q(codename__startswith='change_')
    ).order_by('content_type__model', 'codename')


class TeamAdminCreateForm(UserCreationForm):
    email = forms.EmailField(required=False)
    permissions = forms.ModelMultipleChoiceField(
        queryset=team_permission_queryset(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Only selected Findora model permissions will be granted. Team accounts cannot manage other administrator accounts.',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'permissions')


class TeamAdminUpdateForm(forms.Form):
    is_active = forms.BooleanField(required=False, label='Account is active')
    permissions = forms.ModelMultipleChoiceField(
        queryset=team_permission_queryset(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Uncheck permissions to revoke access.',
    )


class TeamAdminPasswordResetForm(SetPasswordForm):
    pass


class TeamAdminPasswordChangeForm(PasswordChangeForm):
    pass


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'description', 'icon', 'is_active')

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not self.instance.pk or not self.instance.slug:
            generated_slug = slugify(name)
            if generated_slug and Category.objects.filter(slug=generated_slug).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Another category already uses a matching URL slug.')
        return name


class ComplaintAdminForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('status', 'resolution_notes')
        widgets = {'resolution_notes': forms.Textarea(attrs={'rows': 3})}


class ListingAdminForm(forms.ModelForm):
    class Meta:
        model = ServiceListing
        fields = ('title', 'description', 'provider', 'category', 'service_area', 'price_from', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['provider'].queryset = User.objects.filter(
            profile__role=Profile.Role.PROVIDER,
        ).order_by('username')


class SignupForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    role = forms.ChoiceField(choices=Profile.Role.choices)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'role')


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()

    class Meta:
        model = Profile
        fields = ('phone', 'locality')


class ProviderProfileForm(forms.ModelForm):
    class Meta:
        model = ProviderProfile
        fields = ('business_name', 'bio', 'skills', 'experience_years', 'service_areas', 'availability')
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}


class ServiceListingForm(forms.ModelForm):
    class Meta:
        model = ServiceListing
        fields = ('category', 'title', 'description', 'service_area', 'price_from')
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ('issue_description', 'address', 'locality', 'preferred_date', 'preferred_time')
        widgets = {
            'issue_description': forms.Textarea(attrs={'rows': 4}),
            'preferred_date': forms.DateInput(attrs={'type': 'date'}),
            'preferred_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data['preferred_date']
        if preferred_date < timezone.localdate():
            raise forms.ValidationError('Choose today or a future date.')
        return preferred_date


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ('rating', 'comment')
        widgets = {'rating': forms.Select(choices=[(n, f'{n} / 5') for n in range(1, 6)]),
                   'comment': forms.Textarea(attrs={'rows': 3})}


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('booking', 'subject', 'message')
        widgets = {'message': forms.Textarea(attrs={'rows': 4})}

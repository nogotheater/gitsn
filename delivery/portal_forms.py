from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import PermissionDenied, ValidationError
from .domain.products import ordered_products
from .models import Category, Product
from .services.access import audience_for_user


class DeliveryAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '아이디'
        self.fields['password'].label = '비밀번호'

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        try:
            audience_for_user(user)
        except PermissionDenied:
            raise ValidationError('열람 권한이 설정된 계정으로 로그인해 주세요.') from None


class PerformanceFilterForm(forms.Form):
    """Server-validated list conditions. Products and categories are both multi-select (OR)."""
    products = forms.ModelMultipleChoiceField(label='도입 제품', queryset=ordered_products(Product.objects.all()),
                                              required=False, widget=forms.CheckboxSelectMultiple,
                                              help_text='선택한 제품 중 하나 이상 도입한 고객사를 표시합니다.')
    category = forms.MultipleChoiceField(label='고객 분류', choices=Category.choices, required=False,
                                         widget=forms.CheckboxSelectMultiple)
    # Name search narrows the visible list only; it never changes counts or output.
    q = forms.CharField(label='기관명 검색', max_length=100, required=False, strip=True)

    def clean_category(self):
        # Keep the confirmed category order regardless of the order in the request.
        chosen = set(self.cleaned_data['category'])
        return [code for code, _ in Category.choices if code in chosen]

    def product_catalog(self):
        """Every selectable product, in display order, for chips and the mark legend."""
        return [{'id': str(p.pk), 'name': p.name, 'code': p.code, 'marker': p.marker, 'color': p.color}
                for p in self.fields['products'].queryset]


ACCOUNT_ROLES = [('employee', '직원'), ('partner', '파트너사'), ('manager', '기획팀 관리자')]


class AccountCreateForm(forms.Form):
    username = forms.CharField(label='로그인 아이디', max_length=150, validators=get_user_model()._meta.get_field('username').validators)
    first_name = forms.CharField(label='계정 표시 이름', max_length=150, required=False, help_text='사람 또는 업체를 알아보기 위한 선택 항목입니다.')
    role = forms.ChoiceField(label='이용 권한', choices=ACCOUNT_ROLES, initial='employee')
    password1 = forms.CharField(label='비밀번호', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='비밀번호 확인', strip=False, widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        user = get_user_model()(username=data.get('username', ''), first_name=data.get('first_name', ''))
        password_form = SetPasswordForm(user, {'new_password1': data.get('password1', ''), 'new_password2': data.get('password2', '')})
        if not password_form.is_valid():
            for key, errors in password_form.errors.items():
                for error in errors:
                    self.add_error({'new_password1': 'password1', 'new_password2': 'password2'}.get(key), error)
        return data


class AccountEditForm(forms.Form):
    first_name = forms.CharField(label='계정 표시 이름', max_length=150, required=False)
    role = forms.ChoiceField(label='이용 권한', choices=ACCOUNT_ROLES)
    is_active = forms.BooleanField(label='이 계정의 접속 허용', required=False)
    revision = forms.CharField(widget=forms.HiddenInput)


class AccountPasswordForm(SetPasswordForm):
    revision = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = '새 비밀번호'
        self.fields['new_password2'].label = '새 비밀번호 확인'

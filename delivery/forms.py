"""Explicit planning-team input; no hidden automatic merge or delivery tracking."""
from pathlib import Path
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.forms import BaseFormSet, formset_factory
from .domain.duplicates import ContractMergeDecision
from .domain.products import ordered_products
from .domain.quantities import positive_quantity
from .models import Category, Region, DisplayKind, InstitutionType, Organization, Customer, Contract, InstallationSite, Product
from .services.access import require_manager
from .services.customer_location import LOCATION_CATEGORIES, REGION_OF_SIDO, join_location, sido_choices, unit_choices, unit_in_sido

VISIBILITY = [('default', '분류 기본값 따르기'), ('public', '파트너사 공개'), ('private', '파트너사 비공개')]


class PlanningAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '아이디'
        self.fields['password'].label = '비밀번호'

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        try:
            require_manager(user)
        except PermissionDenied:
            raise ValidationError('기획팀 관리 권한이 있는 계정으로 로그인해 주세요.', code='planning_only') from None


class LogoField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, 'size', 0) > 2 * 1024 * 1024:
            raise ValidationError('심볼 파일은 2MB 이하여야 합니다.')
        image = super().to_python(data)
        if image:
            if Path(image.name).suffix.lower() not in {'.png', '.jpg', '.jpeg'} or image.image.format not in {'PNG', 'JPEG'}:
                raise ValidationError('PNG 또는 JPG 이미지 파일을 선택해 주세요.')
        return image


# 설치 장소의 납품현황 표시(2026-11-17 형우): '실적 목록에 표시'·'총 고객사 수에 포함' 두 체크박스를 선택 하나로.
# 따로 두면 '카드 없이 숫자만'·'카드만 있고 숫자 없음' 같은 말이 안 되는 조합이 생겼다.
SITE_DISPLAY = [('none', '납품현황에 표시 안 함 — 이 계약의 설치 장소로만 기록'),
                ('separate', '별도 고객사로 표시 — 납품현황에 카드 추가, 고객사 수 +1')]


def site_display_of(presentation):
    return 'separate' if presentation is not None and (presentation.show_in_list or presentation.include_in_total) else 'none'


def apply_site_display(data):
    shown = data.get('site_display') == 'separate'
    data['show_in_list'] = data['include_in_total'] = shown
    return data


class PresentationForm(forms.Form):
    official_name = forms.CharField(label='공식 명칭', max_length=255)
    category = forms.ChoiceField(label='고객 분류', choices=[('', '분류 선택')] + list(Category.choices),
                                 help_text='해외 금융기관은 해외로 분류합니다. 시청과 의회는 별도 고객사로 등록합니다.')
    region = forms.ChoiceField(label='지역', choices=[('', '지역 선택')] + list(Region.choices), required=False,
                               help_text='지방자치단체·의회는 지역을 선택해야 합니다.')
    include_in_total = forms.BooleanField(label='총 고객사 수에 포함', required=False, initial=True)
    show_in_list = forms.BooleanField(label='실적 목록에 표시', required=False, initial=True)
    display_as = forms.ChoiceField(label='표시 구분', choices=DisplayKind.choices)
    partner_public = forms.ChoiceField(label='파트너사 공개 여부', choices=VISIBILITY, initial='default',
                                      help_text='분류를 변경하면 새 분류의 기본값으로 저장됩니다.')
    logo = LogoField(label='고객사 심볼', required=False,
                    widget=forms.FileInput(attrs={'accept': '.png,.jpg,.jpeg', 'data-logo-input': ''}),
                    help_text='기관 이름 글자 없이 심볼만 있는 파일을 올려 주세요. 기관 누리집의 CI 다운로드 PNG(투명 배경, 긴 변 300px 이상)가 가장 좋습니다. '
                              '여백·배경·크기는 다른 심볼과 같게 자동으로 맞춥니다. PNG·JPG, 2MB 이하.')
    # 심볼 자동 정리(2026-11-17 형우): 손으로 고치는 값은 크기·배경 두 가지뿐
    logo_size = forms.ChoiceField(label='심볼 크기', required=False, initial='normal', widget=forms.RadioSelect(attrs={'data-logo-option': ''}),
                                  choices=[('small', '작게'), ('normal', '보통'), ('large', '크게')],
                                  help_text='미리보기에서 다른 심볼보다 커 보이거나 작아 보이면 바꿔 주세요.')
    logo_background = forms.ChoiceField(label='심볼 배경', required=False, initial='remove', widget=forms.RadioSelect(attrs={'data-logo-option': ''}),
                                        choices=[('remove', '흰 배경 지우기'), ('keep', '배경 유지')],
                                        help_text='흰 바탕이 심볼의 일부(흰 원 안의 마크 등)라 지워지면 안 될 때만 \'유지\'를 고릅니다.')
    logo_auto = forms.BooleanField(label='새 기준으로 자동 정리', required=False, widget=forms.CheckboxInput(attrs={'data-logo-option': ''}),
                                   help_text='이 심볼은 다듬어 올린 그대로 쓰고 있습니다. 켜면 여백·배경·크기를 자동으로 맞춥니다.')
    memo = forms.CharField(label='참고 메모', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    remove_logo = forms.BooleanField(label='기존 심볼 삭제', required=False)
    revision = forms.CharField(required=False, widget=forms.HiddenInput)
    # 4단계(2026-10-22): 고객사 화면에서만 쓴다(with_location=True). 설치 장소·중복 통합 화면에는 없다.
    location_sido = forms.ChoiceField(label='소재지 시·도', required=False, choices=())
    location_unit = forms.ChoiceField(label='소재지 시군구', required=False, choices=())
    institution_type = forms.ChoiceField(label='기관 유형', required=False, choices=InstitutionType.choices,
                                         widget=forms.RadioSelect,
                                         help_text='행정기관은 지도에서 그 시군구 면을 칠하고, 시설·공기업은 점으로만 표시합니다.')

    def __init__(self, *args, with_location=False, for_site=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.with_location = with_location
        self.for_site = for_site
        if for_site:
            del self.fields['show_in_list']
            del self.fields['include_in_total']
            self.fields['site_display'] = forms.ChoiceField(label='납품현황 표시', choices=SITE_DISPLAY, initial='none', required=False,
                                                            help_text='별도 고객사로 표시하면 고객사(계약 당사자)와 따로 카드가 생기고 고객사 수에도 더해집니다.')
        if with_location:
            self.fields['location_sido'].choices = sido_choices()
            self.fields['location_unit'].choices = unit_choices()
            # 고객사 화면 정리(2026-10-22 형우): '실적 목록에 표시'는 뺀다(저장된 값은 그대로, 새 고객사는 표시).
            # 지역(권역)은 지자체·의회에서만 보이고 소재지를 따라간다.
            del self.fields['show_in_list']
            self.fields['region'].help_text = '소재지를 고르면 자동으로 맞춰집니다.'
        else:
            for name in ('location_sido', 'location_unit', 'institution_type'):
                del self.fields[name]

    def clean(self):
        data = super().clean()
        if self.with_location and data.get('category') in LOCATION_CATEGORIES:
            sido, unit = data.get('location_sido', ''), data.get('location_unit', '')
            if unit and not unit_in_sido(unit, sido):
                self.add_error('location_unit', '선택한 시·도 안의 시군구를 골라 주세요.')
            else:
                code = join_location(sido, unit)
                data['location_managed'] = True
                data['location_code'] = code
                if not code:
                    data['institution_type'] = ''
                elif not data.get('institution_type'):
                    self.add_error('institution_type', '기관 유형을 선택해 주세요.')
                # 소재지를 고르면 지역(권역)은 소재지를 따른다. 제주는 권역이 없어 고른 지역을 그대로 둔다.
                if REGION_OF_SIDO.get(sido):
                    data['region'] = REGION_OF_SIDO[sido]
        if self.with_location and data.get('category') and data.get('category') not in LOCATION_CATEGORIES:
            data['region'] = ''   # 다른 분류에서는 지역 칸이 숨는다 — 보이지 않는 값을 남기지 않는다
        if data.get('category') in {Category.LOCAL, Category.COUNCIL} and not data.get('region'):
            self.add_error('region', '지방자치단체·의회는 지역을 선택해 주세요.')
        if data.get('remove_logo') and data.get('logo'):
            self.add_error('logo', '새 심볼 등록과 기존 심볼 삭제 중 하나만 선택해 주세요.')
        if self.for_site:
            apply_site_display(data)
        return data


class ContractForm(forms.Form):
    party_mode = forms.ChoiceField(label='계약 당사자', choices=[('customer', '이 고객사와 같음'), ('existing', '등록된 다른 기관 선택'), ('new', '다른 기관 새로 입력')], initial='customer')
    contracting_party = forms.ModelChoiceField(label='등록된 계약 당사자', queryset=Organization.objects.all().order_by('official_name'), required=False)
    new_party_name = forms.CharField(label='새 계약 당사자 공식 명칭', max_length=255, required=False)
    contract_date = forms.DateField(label='계약일', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    is_active = forms.TypedChoiceField(label='계약 상태', choices=[('active', '유효 계약'), ('ended', '종료 계약')], coerce=lambda value: value == 'active', initial='active')
    source_email_subject = forms.CharField(label='계약 메일 제목', max_length=512, required=False)
    source_email_received_on = forms.DateField(label='메일 수신일', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    source_email_sender = forms.CharField(label='메일 발신자', max_length=255, required=False)
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if data.get('party_mode') == 'existing' and not data.get('contracting_party'):
            self.add_error('contracting_party', '계약 당사자를 선택해 주세요.')
        if data.get('party_mode') == 'new' and not data.get('new_party_name'):
            self.add_error('new_party_name', '계약 당사자의 공식 명칭을 입력해 주세요.')
        return data


class WholeQuantityField(forms.Field):
    widget = forms.TextInput(attrs={'inputmode': 'numeric', 'pattern': '[0-9]+', 'placeholder': '예: 10'})
    def to_python(self, value):
        try:
            return positive_quantity(value)
        except ValueError:
            raise ValidationError('수량은 1 이상의 정수로 입력해 주세요.') from None


class ContractProductForm(forms.Form):
    product = forms.ModelChoiceField(label='제품', queryset=ordered_products(Product.objects.all()))
    quantity = WholeQuantityField(label='수량')


class ProductRows(BaseFormSet):
    default_error_messages = {'too_few_forms': '제품을 한 개 이상 등록해 주세요.'}
    def clean(self):
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            row = form.cleaned_data
            if not row or row.get('DELETE'):
                continue
            product = row['product']
            if product.pk in seen:
                form.add_error('product', '같은 제품은 한 줄에 수량을 합쳐 입력해 주세요.')
            seen.add(product.pk)


class ContractSiteForm(forms.Form):
    existing_site = forms.ModelChoiceField(label='기존 설치 장소', queryset=InstallationSite.objects.all().order_by('official_name'), required=False)
    new_site_name = forms.CharField(label='새 설치 장소 명칭', max_length=255, required=False)
    products = forms.ModelMultipleChoiceField(label='이 장소의 실제 설치 제품', queryset=ordered_products(Product.objects.all()), widget=forms.CheckboxSelectMultiple)
    site_display = forms.ChoiceField(label='납품현황 표시', choices=SITE_DISPLAY, initial='none', required=False)
    update_display = forms.BooleanField(label='기존 장소의 표시 설정도 변경', required=False,
                                       help_text='기존 장소를 재사용할 때 선택합니다. 연결된 다른 계약의 장소 표시에도 적용됩니다.')
    display_revision = forms.CharField(required=False, widget=forms.HiddenInput)
    display_as = forms.ChoiceField(label='표시 구분', choices=DisplayKind.choices, initial=DisplayKind.SITE, required=False)
    category = forms.ChoiceField(label='고객 분류', choices=[('', '고객사와 같은 분류')] + list(Category.choices), required=False)
    region = forms.ChoiceField(label='지역', choices=[('', '고객사와 같은 지역')] + list(Region.choices), required=False)
    partner_public = forms.ChoiceField(label='파트너사 공개 여부', choices=VISIBILITY, initial='default', required=False)

    def clean(self):
        data = super().clean()
        if bool(data.get('existing_site')) == bool(data.get('new_site_name')):
            self.add_error('new_site_name', '기존 장소를 선택하거나 새 장소 명칭을 입력해 주세요. 둘 중 하나만 입력합니다.')
        return apply_site_display(data)


class SiteRows(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            row = form.cleaned_data
            if not row or row.get('DELETE'):
                continue
            key = ('existing', row['existing_site'].pk) if row.get('existing_site') else ('new', row['new_site_name'])
            if key in seen:
                form.add_error('new_site_name', '같은 설치 장소는 한 번만 연결해 주세요.')
            seen.add(key)


ProductFormSet = formset_factory(ContractProductForm, formset=ProductRows, extra=0, min_num=1, validate_min=True, can_delete=True)
SiteFormSet = formset_factory(ContractSiteForm, formset=SiteRows, extra=0, can_delete=True)


class ProductCatalogForm(forms.Form):
    revision = forms.CharField(required=False, widget=forms.HiddenInput)
    code = forms.CharField(label='제품 코드', max_length=64, help_text='예: Alpha-C')
    name = forms.CharField(label='제품명', max_length=255)
    marker = forms.CharField(label='표시 기호', max_length=16, required=False, help_text='예: C 또는 I')
    color = forms.RegexField(label='표시 색상', regex=r'^#[0-9a-fA-F]{6}$', required=False, help_text='선택 입력. 예: #0474D4. 없으면 기본 색상을 사용합니다.')

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance

    def clean_code(self):
        value = self.cleaned_data['code']
        matches = Product.objects.filter(code=value)
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise ValidationError('이미 등록된 제품 코드입니다.')
        return value


class DuplicateSearchForm(forms.Form):
    q = forms.CharField(label='중복 고객사명', max_length=255, required=False)
    duplicates = forms.ModelMultipleChoiceField(label='중복 고객사', queryset=Customer.objects.none(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, candidates=None, **kwargs):
        super().__init__(*args, **kwargs)
        if candidates is not None:
            self.fields['duplicates'].queryset = candidates


class DuplicateContractForm(forms.Form):
    """One row per contract currently held by a duplicate customer being merged away."""
    contract_id = forms.ModelChoiceField(queryset=Contract.objects.all(), widget=forms.HiddenInput)
    action = forms.ChoiceField(label='처리 방법', choices=[('include', '유지할 고객사의 새 계약으로 포함'), ('exclude', '유지할 고객사의 기존 계약과 동일 (중복, 제외)')],
                               initial='include', widget=forms.RadioSelect)
    superseded_by = forms.ModelChoiceField(label='동일한 기존 계약', queryset=Contract.objects.none(), required=False)

    def __init__(self, *args, primary_contracts=None, **kwargs):
        super().__init__(*args, **kwargs)
        if primary_contracts is not None:
            self.fields['superseded_by'].queryset = primary_contracts

    def clean(self):
        data = super().clean()
        if data.get('action') == 'exclude' and not data.get('superseded_by'):
            self.add_error('superseded_by', '제외할 계약은 동일한 기존 계약을 선택해 주세요.')
        return data

    def decision(self):
        data = self.cleaned_data
        superseded = data.get('superseded_by')
        return ContractMergeDecision(contract_id=str(data['contract_id'].pk), action=data['action'],
                                     superseded_by=str(superseded.pk) if superseded else '')


DuplicateContractFormSet = formset_factory(DuplicateContractForm, extra=0)

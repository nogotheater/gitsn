"""Confirmed core structure. No operational/customer records are created here."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from .fields import PositiveQuantityField

class Category(models.TextChoices):
    CENTRAL = "central", "중앙정부"
    PUBLIC = "public", "공공기관"
    LOCAL = "local", "지방자치단체"
    COUNCIL = "council", "지방자치단체 의회"
    FINANCE = "finance", "금융"
    EDUCATION = "education", "교육"
    OVERSEAS = "overseas", "해외"
    PRIVATE = "private", "민간"

class Region(models.TextChoices):
    CAPITAL = "capital", "수도권"
    CHUNGCHEONG = "chungcheong", "충청권"
    HONAM = "honam", "호남권"
    YEONGNAM = "yeongnam", "영남권"
    GANGWON = "gangwon", "강원권"

class InstitutionType(models.TextChoices):
    """지역 현황 지도(8단계): 시군구 면을 칠하는 기관인지 구분한다."""
    ADMIN = "admin", "행정기관"
    FACILITY = "facility", "시설·공기업"

class DisplayKind(models.TextChoices):
    CUSTOMER = "customer", "고객사"
    SITE = "site", "설치 장소"

class IdentifiedRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Organization(IdentifiedRecord):
    official_name = models.CharField("공식 명칭", max_length=255)

    def __str__(self):
        return self.official_name

class PresentationFields(IdentifiedRecord):
    # Creating a presentation represents an explicit intent to show this target.
    # A physical InstallationSite alone still creates no list entry.
    show_in_list = models.BooleanField("목록에 표시", default=True)
    category = models.CharField("고객 분류", max_length=16, choices=Category.choices)
    region = models.CharField("지역", max_length=16, choices=Region.choices, blank=True)
    # No unconditional public default: factories apply the confirmed category rule.
    partner_public = models.BooleanField("파트너사 공개 여부")
    logo = models.ImageField("심볼", upload_to="logos/", blank=True)
    memo = models.TextField("참고 메모", blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.category in {Category.LOCAL, Category.COUNCIL} and not self.region:
            raise ValidationError({"region": "지방자치단체와 의회는 지역이 필요합니다."})

class Customer(PresentationFields):
    display_as = models.CharField("표시 구분", max_length=16, choices=DisplayKind.choices, default=DisplayKind.CUSTOMER)
    organization = models.OneToOneField(Organization, on_delete=models.PROTECT, related_name="customer")
    include_in_total = models.BooleanField("고객사 수에 포함", default=True)
    # Manual duplicate consolidation only (stage 6). Never set automatically.
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="merged_duplicates")
    merged_at = models.DateTimeField("통합된 일시", null=True, blank=True)
    # 지역 현황 지도(8단계). 모두 선택 입력이다.
    # location_code: 면 코드(5자리) 또는 시·도 코드(2자리). 값 목록은 delivery.domain.admin_areas가
    # 관리하고 모델에는 choices를 걸지 않는다(경계 갱신 때 마이그레이션이 생기지 않게).
    location_code = models.CharField("소재지", max_length=5, blank=True)
    institution_type = models.CharField("기관 유형", max_length=16, choices=InstitutionType.choices, blank=True)

    class Meta:
        permissions = [("manage_delivery", "Can manage delivery data and local accounts")]

    def __str__(self):
        return str(self.organization)

class InstallationSite(IdentifiedRecord):
    official_name = models.CharField("설치 장소 명칭", max_length=255)

    def __str__(self):
        return self.official_name

class SitePresentation(PresentationFields):
    """Optional presentation for a place; a physical place alone creates no extra customer."""
    site = models.OneToOneField(InstallationSite, on_delete=models.PROTECT, related_name="presentation")
    display_as = models.CharField("표시 구분", max_length=16, choices=DisplayKind.choices, default=DisplayKind.SITE)
    include_in_total = models.BooleanField("고객사 수에 포함", default=False)

class Product(IdentifiedRecord):
    code = models.CharField("제품 코드", max_length=64, unique=True)
    name = models.CharField("제품명", max_length=255)
    marker = models.CharField("제품 표시 기호", max_length=16, blank=True)
    color = models.CharField("제품 표시 색상", max_length=32, blank=True)

    def __str__(self):
        return self.name

class Contract(IdentifiedRecord):
    contracting_party = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="signed_contracts")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="contracts")
    contract_date = models.DateField("계약일", null=True, blank=True)
    is_active = models.BooleanField("유효 계약")
    source_email_subject = models.CharField("계약 메일 제목", max_length=512, blank=True)
    source_email_received_on = models.DateField("메일 수신일", null=True, blank=True)
    source_email_sender = models.CharField("메일 발신자", max_length=255, blank=True)
    # Set only by manual duplicate-customer merges (stage 6), never automatically.
    # The surviving contract this one duplicates; history stays, current totals do not double count it.
    superseded_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="supersedes")

    def clean(self):
        super().clean()
        if self.superseded_by_id:
            if self.superseded_by_id == self.pk:
                raise ValidationError({"superseded_by": "같은 계약을 선택할 수 없습니다."})
            if self.is_active:
                raise ValidationError({"superseded_by": "중복으로 표시한 계약은 유효 계약일 수 없습니다."})
            if self.customer_id and self.superseded_by.customer_id != self.customer_id:
                raise ValidationError({"superseded_by": "선택한 계약은 같은 고객사로 통합된 계약이어야 합니다."})

class ContractProduct(IdentifiedRecord):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="product_lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="contract_lines")
    quantity = PositiveQuantityField("제품 수량")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract", "product"], name="unique_contract_product"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="contract_quantity_positive"),
        ]

class ContractSite(IdentifiedRecord):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="site_links")
    site = models.ForeignKey(InstallationSite, on_delete=models.PROTECT, related_name="contract_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract", "site"], name="unique_contract_site"),
        ]

class SiteProductSelection(IdentifiedRecord):
    contract_site = models.ForeignKey(ContractSite, on_delete=models.PROTECT, related_name="product_selections")
    contract_product = models.ForeignKey(ContractProduct, on_delete=models.PROTECT, related_name="site_selections")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract_site", "contract_product"], name="unique_site_product_selection"),
        ]

    def clean(self):
        super().clean()
        if self.contract_site_id and self.contract_product_id:
            if self.contract_site.contract_id != self.contract_product.contract_id:
                raise ValidationError("설치 장소와 제품의 계약이 일치하지 않습니다.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

class UserAccessProfile(IdentifiedRecord):
    class Audience(models.TextChoices):
        EMPLOYEE = "employee", "직원"
        PARTNER = "partner", "파트너사"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="delivery_access")
    audience = models.CharField(max_length=16, choices=Audience.choices)
    # Planning-team management uses Django's manage_delivery permission, not another audience.

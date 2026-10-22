"""고객사 삭제(2026-10-22 형우): 계약이 있어도 지우고, 확인 화면을 거친다."""
from tempfile import TemporaryDirectory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from delivery.models import (
    Contract, ContractProduct, ContractSite, Customer, InstallationSite, Organization, Product,
    SitePresentation, SiteProductSelection, UserAccessProfile,
)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerDeleteHttp(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user('del-manager', password='LocalDelOnly!41')
        UserAccessProfile.objects.create(user=cls.manager, audience='employee')
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.employee = User.objects.create_user('del-employee', password='LocalDelOnly!41')
        UserAccessProfile.objects.create(user=cls.employee, audience='employee')
        cls.product = Product.objects.create(code='del-p', name='가상 삭제 P', marker='P')

    def setUp(self):
        self.client.force_login(self.manager)
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))

    def customer(self, name, **fields):
        return Customer.objects.create(organization=Organization.objects.create(official_name=name), category='local',
                                       region='capital', partner_public=True, **fields)

    def contract(self, customer, active=True, party=None):
        contract = Contract.objects.create(customer=customer, contracting_party=party or customer.organization, is_active=active)
        line = ContractProduct.objects.create(contract=contract, product=self.product, quantity=1)
        return contract, line

    def link(self, contract, line, site):
        link = ContractSite.objects.create(contract=contract, site=site)
        SiteProductSelection.objects.create(contract_site=link, contract_product=line)

    def test_confirm_page_lists_what_goes_and_deletes_nothing(self):
        target = self.customer('삭제 가상 시청')
        self.contract(target)
        self.contract(target, active=False)
        response = self.client.get(reverse('planning-customer-delete', args=[target.pk]))
        self.assertContains(response, '2건 (유효 1건 · 종료 1건)')
        self.assertContains(response, '되돌릴 수 없습니다')
        self.assertTrue(Customer.objects.filter(pk=target.pk).exists())
        self.assertContains(self.client.get(reverse('planning-customer-detail', args=[target.pk])),
                            reverse('planning-customer-delete', args=[target.pk]))

    def test_delete_removes_contracts_own_sites_and_duplicates_but_keeps_shared_data(self):
        target = self.customer('삭제 가상 시청')
        other = self.customer('남는 가상 군청')
        shared_party = Organization.objects.create(official_name='공동 계약 가상 기관')
        active, active_line = self.contract(target, party=shared_party)
        ended, _ = self.contract(target, active=False)
        own_site = InstallationSite.objects.create(official_name='삭제 가상 장소')
        SitePresentation.objects.create(site=own_site, category='local', region='capital', partner_public=True)
        shared_site = InstallationSite.objects.create(official_name='공유 가상 장소')
        self.link(active, active_line, own_site)
        self.link(active, active_line, shared_site)
        other_contract, other_line = self.contract(other, party=shared_party)
        self.link(other_contract, other_line, shared_site)
        duplicate = self.customer('삭제 가상 시청(중복)', merged_into=target, merged_at=timezone.now(),
                                  show_in_list=False, include_in_total=False)

        response = self.client.post(reverse('planning-customer-delete', args=[target.pk]), follow=True)
        self.assertRedirects(response, reverse('planning-home'))
        self.assertContains(response, '고객사를 삭제했습니다')
        self.assertFalse(Customer.objects.filter(pk__in=[target.pk, duplicate.pk]).exists())
        self.assertFalse(Contract.objects.filter(pk__in=[active.pk, ended.pk]).exists())
        self.assertFalse(InstallationSite.objects.filter(pk=own_site.pk).exists())
        self.assertFalse(Organization.objects.filter(official_name__in=['삭제 가상 시청', '삭제 가상 시청(중복)']).exists())
        # 남는 것: 다른 계약에도 쓰인 장소·계약 상대 기관, 다른 고객사, 제품
        self.assertTrue(InstallationSite.objects.filter(pk=shared_site.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=shared_party.pk).exists())
        self.assertTrue(Contract.objects.filter(pk=other_contract.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_deleted_customer_leaves_performance_counts(self):
        target = self.customer('삭제 가상 시청')
        self.contract(target)
        before = self.client.get(reverse('performance')).context['counts']['total']
        self.client.post(reverse('planning-customer-delete', args=[target.pk]))
        self.assertEqual(self.client.get(reverse('performance')).context['counts']['total'], before - 1)

    def test_non_manager_cannot_delete(self):
        target = self.customer('삭제 가상 시청')
        self.client.force_login(self.employee)
        self.assertEqual(self.client.post(reverse('planning-customer-delete', args=[target.pk])).status_code, 403)
        self.assertTrue(Customer.objects.filter(pk=target.pk).exists())

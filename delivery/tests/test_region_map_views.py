"""지역 현황 화면 접근 권한(6a). 직원만 볼 수 있다."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from delivery.models import UserAccessProfile


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegionMapAccessScenarios(TestCase):
    def user(self, name, audience):
        u = get_user_model().objects.create_user(name, password='LocalExample!77')
        UserAccessProfile.objects.create(user=u, audience=audience)
        return u

    def test_employee_sees_the_page_with_data(self):
        self.client.force_login(self.user('rm-employee', 'employee'))
        r = self.client.get('/performance/map/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="rmap-data"')
        self.assertContains(r, 'delivery/map/korea-lite.json')
        self.assertContains(r, 'vuski/admdongkor')

    def test_partner_is_denied(self):
        self.client.force_login(self.user('rm-partner', 'partner'))
        self.assertEqual(self.client.get('/performance/map/').status_code, 403)

    def test_anonymous_goes_to_login(self):
        r = self.client.get('/performance/map/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])


    def test_menu_link_only_for_employees(self):
        self.client.force_login(self.user('rm-employee-2', 'employee'))
        self.assertContains(self.client.get('/performance/'), 'href="/performance/map/"')
        self.client.force_login(self.user('rm-partner-2', 'partner'))
        self.assertNotContains(self.client.get('/performance/'), 'href="/performance/map/"')


    def test_database_error_shows_a_notice_with_503(self):
        from unittest import mock
        from django.db import DatabaseError
        self.client.force_login(self.user('rm-employee-3', 'employee'))
        with mock.patch('delivery.services.region_map.region_map_payload', side_effect=DatabaseError('down')):
            r = self.client.get('/performance/map/')
        self.assertEqual(r.status_code, 503)
        self.assertContains(r, '새로고침해 주십시오', status_code=503)
        self.assertNotContains(r, 'id="rmap-data"', status_code=503)

    def test_unassigned_list_only_for_managers(self):
        from django.contrib.auth.models import Permission
        from delivery.models import Category, Contract, ContractProduct, Customer, Organization, Product, Region
        p = Product.objects.create(code='rmv-s', name='Alpha-S', marker='S')
        cu = Customer.objects.create(organization=Organization.objects.create(official_name='소재지 없는 군청'),
                                     category=Category.LOCAL, region=Region.CHUNGCHEONG, partner_public=True)
        k = Contract.objects.create(customer=cu, contracting_party=cu.organization, is_active=True)
        ContractProduct.objects.create(contract=k, product=p, quantity=1)
        self.client.force_login(self.user('rm-employee-4', 'employee'))
        combos = self.client.get('/performance/map/').context['payload']['combos']
        self.assertEqual([c['unassigned'] for c in combos.values()], [[]] * 4)
        m = self.user('rm-manager-4', 'employee')
        m.user_permissions.add(Permission.objects.get(codename='manage_delivery', content_type__app_label='delivery'))
        self.client.force_login(m)
        combos = self.client.get('/performance/map/').context['payload']['combos']
        self.assertEqual([o['name'] for o in combos['eavesdrop:local']['unassigned']], ['소재지 없는 군청'])

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

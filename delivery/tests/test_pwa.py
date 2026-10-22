"""홈 화면 앱(PWA, 2026-10-22 형우): 폰에서 '홈 화면에 추가'로 앱처럼 쓰기."""
import json
from django.conf import settings
from django.test import TestCase


class HomeScreenApp(TestCase):
    def test_manifest_icons_and_service_worker_are_served(self):
        manifest = json.loads((settings.BASE_DIR / 'static/delivery/pwa/manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual((manifest['start_url'], manifest['display']), ('/performance/', 'standalone'))
        for icon in manifest['icons']:
            self.assertTrue((settings.BASE_DIR / icon['src'].lstrip('/').replace('static/', 'static/', 1)).is_file(), icon['src'])
        response = self.client.get('/sw.js')   # 로그인 없이, 사이트 맨 위 주소에서
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])
        self.assertNotIn('caches.open', response.content.decode())   # 고객 자료를 폰에 저장하지 않는다

    def test_pages_link_the_manifest_and_icon(self):
        login = self.client.get('/login/')
        self.assertContains(login, 'rel="manifest"')
        self.assertContains(login, 'apple-touch-icon')
        self.assertContains(login, "serviceWorker.register('/sw.js')")

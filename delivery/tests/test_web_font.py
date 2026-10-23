"""웹 글꼴 나누기(2026-10-23, 형우 '하나씩 진행하자' → 3번 글꼴). 화면은 작은 woff2 두 개, 인쇄·PDF는 원본 TTF."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase

FONTS = Path(settings.BASE_DIR) / 'static' / 'delivery' / 'fonts'


class WebFontScenarios(SimpleTestCase):
    def test_screens_use_small_split_woff2_and_print_keeps_original(self):
        core, ext = FONTS / 'FreesentationVF-core.woff2', FONTS / 'FreesentationVF-ext.woff2'
        for path in (core, ext):
            self.assertEqual(path.read_bytes()[:4], b'wOF2')
        self.assertLess(core.stat().st_size, 800 * 1024)          # 처음 받는 글꼴은 1MB 아래(전에는 6.8MB)
        self.assertTrue((FONTS / 'FreesentationVF.ttf').exists())   # PDF에 넣는 원본은 그대로
        css = (Path(settings.BASE_DIR) / 'static' / 'delivery' / 'planning.css').read_text(encoding='utf-8')
        self.assertNotIn('FreesentationVF.ttf', css)
        # 나머지 한글·한자 파일은 그런 글자가 있을 때만(unicode-range), 기본 파일은 범위 없이 뒤에 둬서 먼저 쓴다
        self.assertLess(css.index('FreesentationVF-ext.woff2'), css.index('FreesentationVF-core.woff2'))
        self.assertIn('unicode-range:U+AC00-D7A3', css)

"""행정구역 목록(지역 현황 지도의 면·시·도) 검사. DB를 쓰지 않는다."""
from collections import Counter
from unittest import TestCase

from delivery.domain import admin_areas as aa


class AdminAreaScenarios(TestCase):
    def test_sixteen_sido_after_jeonnam_gwangju_merger(self):
        self.assertEqual(len(aa.SIDO), 16)
        self.assertEqual(aa.SIDO_BY_CODE['12'][0], '전남광주통합특별시')

    def test_229_units_are_227_local_governments_plus_sejong_and_jeju(self):
        self.assertEqual(len(aa.UNITS), 229)
        whole = [code for code, _n, _s, w in aa.UNITS if w]
        self.assertEqual(sorted(whole), ['36110', '50000'])
        self.assertEqual(len({code for code, *_ in aa.UNITS}), 229)

    def test_general_districts_are_merged_into_their_city(self):
        self.assertEqual(aa.GENERAL_DISTRICTS['41111'], '41110')  # 수원시장안구 → 수원시
        self.assertEqual(aa.GENERAL_DISTRICTS['44131'], '44130')  # 천안시동남구 → 천안시
        names = {name for _c, name, *_ in aa.UNITS}
        self.assertNotIn('수원시장안구', names)
        self.assertIn('천안시', names)

    def test_incheon_has_eleven_units_after_2026_reorganization(self):
        incheon = {aa.UNIT_BY_CODE[c][0] for c in aa.units_in('28')}
        self.assertEqual(len(incheon), 11)
        self.assertTrue({'영종구', '제물포구', '서해구', '검단구'} <= incheon)
        self.assertNotIn('중구', incheon)

    def test_sido_of_accepts_unit_and_sido_codes(self):
        self.assertEqual(aa.sido_of('44130'), '44')
        self.assertEqual(aa.sido_of('41'), '41')
        self.assertIsNone(aa.sido_of('99999'))

    def test_units_per_sido_add_up(self):
        per = Counter(sido for _c, _n, sido, _w in aa.UNITS)
        self.assertEqual(sum(per.values()), 229)
        self.assertEqual(set(per), set(aa.SIDO_BY_CODE))

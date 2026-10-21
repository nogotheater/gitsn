"""고객사 이름 → 소재지·기관 유형 추정 규칙 검사. DB를 쓰지 않는다."""
from unittest import TestCase

from delivery.domain.locations import ADMIN, FACILITY, guess_location


class LocationGuessScenarios(TestCase):
    def check(self, name, category, region, code, kind):
        g = guess_location(name, category, region)
        self.assertEqual((g.location_code, g.institution_type), (code, kind), g.reason)
        return g

    def test_city_hall_name_with_or_without_suffix(self):
        self.check('천안시청', 'local', 'chungcheong', '44130', ADMIN)
        self.check('천안시', 'local', 'chungcheong', '44130', ADMIN)

    def test_city_with_general_districts_maps_to_the_city(self):
        self.check('수원시청', 'local', 'capital', '41110', ADMIN)

    def test_same_name_is_split_by_region(self):
        self.check('광주시청', 'local', 'capital', '41610', ADMIN)      # 경기 광주시
        self.check('남구청', 'local', 'honam', '12270', ADMIN)          # 전남광주 남구
        self.check('고성군청', 'local', 'yeongnam', '48820', ADMIN)     # 경남 고성군
        self.check('고성군', 'local', 'gangwon', '51820', ADMIN)        # 강원 고성군

    def test_same_name_inside_one_region_is_left_for_people(self):
        g = self.check('남구청', 'local', 'yeongnam', '', ADMIN)
        self.assertIn('후보 여러 곳', g.reason)

    def test_sido_prefixed_district(self):
        self.check('대구광역시 남구청', 'local', 'yeongnam', '27200', ADMIN)
        self.check('서울특별시 강서구의회', 'council', 'capital', '11500', ADMIN)

    def test_sido_level_offices_use_sido_code(self):
        self.check('경기도청', 'local', 'capital', '41', ADMIN)
        self.check('경기도', 'council', 'capital', '41', ADMIN)
        self.check('전남광주통합특별시 (광주청사)', 'local', 'honam', '12', ADMIN)
        self.check('전라북도', 'council', 'honam', '52', ADMIN)  # 예전 이름

    def test_sejong_and_jeju_offices_paint_their_single_unit(self):
        self.check('세종특별자치시', 'local', 'chungcheong', '36110', ADMIN)

    def test_facilities(self):
        self.check('영천시 청소년수련관', 'local', 'yeongnam', '47230', FACILITY)
        self.check('고흥군 대서면사무소', 'local', 'honam', '12740', FACILITY)
        self.check('충청남도개발공사', 'local', 'chungcheong', '44', FACILITY)
        self.check('서울특별시립 아동푸른센터', 'local', 'capital', '11', FACILITY)

    def test_facility_without_place_in_name_is_left_blank(self):
        self.check('세종문화회관', 'local', 'capital', '', FACILITY)
        self.check('왕산해수욕장', 'local', 'capital', '', FACILITY)

    def test_combined_record_with_middle_dot_counts_as_the_office(self):
        self.check('종로구·마로니에공원', 'local', 'capital', '11110', ADMIN)

    def test_incheon_old_district_needs_a_choice(self):
        g = self.check('인천광역시 중구', 'local', 'capital', '', ADMIN)
        self.assertIn('영종구', g.reason)


class LocationTextScenarios(TestCase):
    def test_format_and_parse_round_trip(self):
        from delivery.domain.locations import format_location, parse_location
        for code in ('44130', '41', '12', '28155', '36110', '50000', '41110'):
            self.assertEqual(parse_location(format_location(code)), code)

    def test_parse_accepts_codes_full_names_and_blank(self):
        from delivery.domain.locations import parse_location
        self.assertEqual(parse_location('44130'), '44130')
        self.assertEqual(parse_location('인천 영종구'), '28155')
        self.assertEqual(parse_location('충청남도 천안시'), '44130')
        self.assertEqual(parse_location('세종'), '36110')
        self.assertEqual(parse_location('  '), '')

    def test_parse_rejects_unknown_places(self):
        from delivery.domain.locations import parse_location
        with self.assertRaises(ValueError):
            parse_location('인천 중구')   # 2026-07 개편으로 없어진 이름
        with self.assertRaises(ValueError):
            parse_location('어딘가 무슨구')


class LocationGuessFixes(TestCase):
    """3단계 대조표에서 찾은 실제 이름 형식(2026-10-21)."""
    def test_special_city_name(self):
        g = guess_location('수원특례시', 'local', 'capital')
        self.assertEqual((g.location_code, g.institution_type), ('41110', ADMIN))

    def test_office_combined_with_facility(self):
        g = guess_location('포항시청·포항중앙상가', 'local', 'yeongnam')
        self.assertEqual((g.location_code, g.institution_type), ('47110', ADMIN))

    def test_branch_office_without_parentheses(self):
        g = guess_location('전남광주통합특별시 광주청사', 'local', 'honam')
        self.assertEqual((g.location_code, g.institution_type), ('12', ADMIN))

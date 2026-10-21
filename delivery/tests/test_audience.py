"""Disclosure and authorization business scenarios; no database required."""
from dataclasses import replace
import json
from types import SimpleNamespace
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from delivery.domain.audience import ProductBadge, TargetRecord, project_targets
from delivery.services.access import audience_for_user, require_employee, require_manager
from delivery.services.audience_performance import current_performance_payload, contract_source_metadata


def actor(audience='employee', *, active=True, authenticated=True, manager=False):
    return SimpleNamespace(is_authenticated=authenticated, is_active=active,
                           delivery_access=SimpleNamespace(audience=audience),
                           has_perm=lambda permission: manager)


def target(index, *, public=True, counted=True, listed=True, category='public', kind='customer'):
    return TargetRecord(str(index), kind, category, '', listed, counted, public,
                        name=('PUBLIC_' if public else 'SECRET_') + str(index), has_logo=True,
                        products=(ProductBadge('badge-' + str(index), 'PRODUCT_' + str(index), 'C', '#123456'),))


class AudienceProjectionScenarios(SimpleTestCase):
    def test_display_label_does_not_change_identity_or_count(self):
        customer = target(1)
        place = replace(customer, kind='site', display_as='customer')
        payload = project_targets([customer, place], audience='employee')
        self.assertEqual(payload['counts']['total'], 2)
        self.assertEqual(payload['items'][1]['kind'], 'site')
        self.assertEqual(payload['items'][1]['display_as'], 'customer')

    def test_seventy_public_thirty_private_equal_total_without_private_rows(self):
        records = [target(i) for i in range(70)] + [target(i, public=False, category='private') for i in range(70, 100)]
        employee = project_targets(records, audience='employee')
        partner = project_targets(records, audience='partner')
        self.assertEqual(employee['counts'], partner['counts'])
        self.assertEqual(partner['counts']['total'], 100)
        self.assertEqual(partner['counts']['public'], 70)
        self.assertEqual(partner['counts']['private'], 30)
        self.assertEqual(len(employee['items']), 100)
        self.assertEqual(len(partner['items']), 70)
        serialized = json.dumps(partner)
        self.assertNotIn('SECRET_', serialized)
        for i in range(70, 100):
            self.assertNotIn('PRODUCT_' + str(i), serialized)
            self.assertNotIn('badge-' + str(i), serialized)
        self.assertEqual(partner['counts']['private_by_category'], {'private': 30})

    def test_unlisted_still_counted_and_uncounted_place_still_listed(self):
        records = [target(1), target(2, public=False, listed=False), target(3, counted=False, kind='site')]
        employee = project_targets(records, audience='employee')
        partner = project_targets(records, audience='partner')
        self.assertEqual(employee['counts'], partner['counts'])
        self.assertEqual(partner['counts']['total'], 2)
        self.assertEqual(partner['counts']['private'], 1)
        self.assertEqual(len(partner['items']), 2)

    def test_private_uncounted_place_has_neither_row_nor_extra_customer_count(self):
        data = project_targets([target(1, public=False, counted=False, kind='site')], audience='partner')
        self.assertEqual(data['items'], [])
        self.assertEqual(data['counts']['total'], 0)
        self.assertEqual(data['counts']['private'], 0)

    def test_same_target_counted_once_but_customer_and_place_are_distinct(self):
        original = target(1)
        data = project_targets([original, original, replace(original, kind='site')], audience='employee')
        self.assertEqual(data['counts']['total'], 2)
        self.assertEqual(len(data['items']), 2)
        with self.assertRaises(ValueError):
            project_targets([original, replace(original, partner_public=False)], audience='partner')

    def test_list_output_is_a_whitelist_without_quantities_memo_or_source(self):
        item = project_targets([target(1)], audience='employee')['items'][0]
        self.assertEqual(set(item), {'id', 'kind', 'display_as', 'name', 'category', 'region', 'has_logo', 'products'})
        self.assertEqual(set(item['products'][0]), {'id', 'name', 'marker', 'color'})
        with self.assertRaises(ValueError):
            project_targets([], audience='admin')


class AccessBoundaryScenarios(SimpleTestCase):
    def test_anonymous_and_inactive_users_denied_before_data_queries(self):
        for user in [AnonymousUser(), actor(active=False), actor(authenticated=False)]:
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                current_performance_payload(user)

    def test_missing_and_unknown_profiles_do_not_gain_employee_access(self):
        for user in [SimpleNamespace(is_authenticated=True, is_active=True), actor('admin'), actor(None)]:
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                audience_for_user(user)

    def test_only_employee_with_manager_permission_can_manage_or_read_sources(self):
        require_manager(actor(manager=True))
        for user in [actor(), actor('partner'), actor('partner', manager=True)]:
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                require_manager(user)
            with self.assertRaises(PermissionDenied):
                contract_source_metadata(user, 'unreachable-contract')

    def test_partners_cannot_gain_employee_detail_access_with_manager_permission(self):
        require_employee(actor())
        with self.assertRaises(PermissionDenied):
            require_employee(actor('partner', manager=True))

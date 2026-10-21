from unittest.mock import Mock
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from delivery.portal_forms import AccountCreateForm, AccountEditForm, DeliveryAuthenticationForm, PerformanceFilterForm
from django.core.exceptions import ValidationError


class PortalInputScenarios(SimpleTestCase):
    def test_categories_are_multi_select_in_confirmed_order_and_search_is_trimmed(self):
        form = PerformanceFilterForm({'category': ['education', 'central', 'education'], 'q': '  가상 시청 '})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['category'], ['central', 'education'])
        self.assertEqual(form.cleaned_data['q'], '가상 시청')
        self.assertNotIn('region', form.fields)

    def test_empty_filter_is_all_and_invalid_codes_are_not_silently_ignored(self):
        form = PerformanceFilterForm({})
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.cleaned_data['products']), [])
        self.assertEqual(form.cleaned_data['category'], [])
        self.assertEqual(form.cleaned_data['q'], '')
        for data in [{'category': ['invented']}, {'category': ['public', 'invented']}, {'products': ['not-a-uuid']}, {'q': 'x' * 101}]:
            self.assertFalse(PerformanceFilterForm(data).is_valid())

    def test_weak_or_mismatched_password_and_invalid_role_rejected(self):
        data = {'username': 'new-example', 'role': 'employee', 'password1': '123', 'password2': '123'}
        self.assertFalse(AccountCreateForm(data).is_valid())
        self.assertFalse(AccountCreateForm({**data, 'password1': 'LocalExample!72', 'password2': 'Different!73'}).is_valid())
        self.assertFalse(AccountEditForm({'role': 'superuser', 'revision': 'test'}).is_valid())

    def test_password_inputs_never_render_supplied_values(self):
        form = AccountCreateForm({'password1': 'NeverEchoExample!72', 'password2': 'NeverEchoExample!72'})
        self.assertNotIn('NeverEchoExample!72', str(form['password1']))
        self.assertNotIn('NeverEchoExample!72', str(form['password2']))

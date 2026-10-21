"""A city and a separately shown installation place need not count as two."""
from django.test import SimpleTestCase
from delivery.domain.target_selection import select_target_ids
from delivery.models import Category, InstallationSite, Organization
from delivery.services.presentations import new_customer, new_site_presentation


class ListAndCountScenarios(SimpleTestCase):
    def make_targets(self):
        return (
            new_customer(organization=Organization(official_name="가상 시청"),
                         category=Category.PUBLIC, show_in_list=True),
            new_site_presentation(site=InstallationSite(official_name="가상 해수욕장"),
                                  category=Category.PUBLIC, show_in_list=True),
        )

    def select(self, customer, site):
        return select_target_ids([
            (("customer", customer.pk), customer.show_in_list, customer.include_in_total),
            (("site", site.pk), site.show_in_list, site.include_in_total),
        ])

    def test_city_and_place_can_both_be_listed_but_total_is_one(self):
        customer, site = self.make_targets()
        listed, counted = self.select(customer, site)
        self.assertEqual(len(listed), 2)
        self.assertEqual(counted, {("customer", customer.pk)})

    def test_including_exceptional_place_changes_count_without_adding_list_entry(self):
        customer, site = self.make_targets()
        before, _ = self.select(customer, site)
        site.include_in_total = True
        listed, counted = self.select(customer, site)
        self.assertEqual(listed, before)
        self.assertEqual(len(counted), 2)

    def test_hiding_a_list_entry_does_not_rewrite_count_or_partner_visibility(self):
        customer, site = self.make_targets()
        customer.show_in_list = False
        listed, counted = self.select(customer, site)
        self.assertEqual(listed, {("site", site.pk)})
        self.assertEqual(counted, {("customer", customer.pk)})
        self.assertTrue(customer.partner_public)

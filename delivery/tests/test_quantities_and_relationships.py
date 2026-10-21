"""Tests use unsaved objects; no claim of DB constraint verification."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from delivery.domain.quantities import positive_quantity
from delivery.fields import PositiveQuantityField
from delivery.models import (
    Organization, Customer, InstallationSite, Contract, ContractProduct,
    ContractSite, SiteProductSelection, Product, Category,
)
from delivery.services.presentations import new_customer, new_site_presentation, change_category

class QuantityInputScenarios(SimpleTestCase):
    def test_normal_whole_units_from_forms_and_domain(self):
        for value in [1, 15, "1", "15", " 15 "]:
            with self.subTest(value=value):
                self.assertEqual(positive_quantity(value), int(value))

    def test_invalid_values_do_not_get_truncated_or_coerced(self):
        field = PositiveQuantityField()
        for value in [None, "", " ", 0, "0", -1, "-1", 1.5, 1.0, "1.5", "1.0",
                      True, False, Decimal("1.5"), "1e2"]:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    positive_quantity(value)
                with self.assertRaises(ValidationError):
                    field.get_prep_value(value)
                with self.assertRaises(ValidationError):
                    field.formfield().clean(value)

class RelationshipScenarios(SimpleTestCase):
    def context(self):
        organization = Organization(official_name="가상 기관")
        customer = new_customer(organization=organization, category=Category.PUBLIC)
        return Contract(contracting_party=organization, customer=customer, is_active=True)

    def test_same_contract_place_can_select_its_product(self):
        contract = self.context()
        line = ContractProduct(contract=contract, product=Product(code="demo-c", name="가상 제품"), quantity=10)
        place = ContractSite(contract=contract, site=InstallationSite(official_name="가상 장소"))
        SiteProductSelection(contract_site=place, contract_product=line).clean()

    def test_place_cannot_select_a_product_from_another_contract(self):
        contract, other_contract = self.context(), self.context()
        line = ContractProduct(contract=other_contract, product=Product(code="demo-c", name="가상 제품"), quantity=10)
        place = ContractSite(contract=contract, site=InstallationSite(official_name="가상 장소"))
        with self.assertRaises(ValidationError):
            SiteProductSelection(contract_site=place, contract_product=line).clean()

    def test_public_defaults_and_manual_choices_are_independent_of_count(self):
        organization = Organization(official_name="가상 민간")
        customer = new_customer(organization=organization, category=Category.PRIVATE)
        self.assertTrue(customer.include_in_total)
        self.assertFalse(customer.partner_public)
        site = new_site_presentation(site=InstallationSite(official_name="가상 장소"), category=Category.PUBLIC)
        self.assertFalse(site.include_in_total)
        self.assertTrue(site.partner_public)
        change_category(customer, Category.PUBLIC)
        self.assertTrue(customer.partner_public)

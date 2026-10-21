"""Business examples for any-selected-product search across current contracts."""
from unittest import TestCase
from delivery.domain.aggregates import ContractProductQuantity as Line
from delivery.domain.lifecycle import ContractSnapshot as Contract
from delivery.domain.product_filters import matching_current_customer_ids, products_match_any


class ProductFilterScenarios(TestCase):
    def setUp(self):
        self.contracts = (
            Contract("both-c", "both", True, (Line("both-c", "C", 10),)),
            Contract("both-i", "both", True, (Line("both-i", "I", 5),)),
            Contract("c-only", "only-c", True, (Line("c-only", "C", 2),)),
            Contract("i-only", "only-i", True, (Line("i-only", "I", 3),)),
            Contract("ended-c", "partial", False, (Line("ended-c", "C", 4),)),
            Contract("active-i", "partial", True, (Line("active-i", "I", 1),)),
            Contract("ended", "closed", False, (Line("ended", "C", 1),)),
        )

    def test_any_selected_product_matches_without_duplicating_a_customer(self):
        self.assertEqual(matching_current_customer_ids(self.contracts, ["C", "I"]), {"both", "only-c", "only-i", "partial"})

    def test_one_product_and_duplicate_selection_do_not_duplicate_customer(self):
        self.assertEqual(matching_current_customer_ids(self.contracts, ["C", "C"]), {"both", "only-c"})

    def test_clearing_product_selection_keeps_all_current_customers(self):
        self.assertEqual(matching_current_customer_ids(self.contracts, []), {"both", "only-c", "only-i", "partial"})

    def test_each_place_uses_its_own_products_and_needs_any_selected_product(self):
        self.assertTrue(products_match_any(["C"], ["C", "I"]))
        self.assertTrue(products_match_any(["I"], ["C", "I"]))
        self.assertTrue(products_match_any(["C", "I", "bell"], ["C", "I"]))

    def test_unrelated_or_ended_only_products_do_not_match(self):
        self.assertFalse(products_match_any(["S"], ["C", "I"]))
        self.assertEqual(matching_current_customer_ids(self.contracts, ["S"]), set())
        self.assertTrue(products_match_any(["C"], []))

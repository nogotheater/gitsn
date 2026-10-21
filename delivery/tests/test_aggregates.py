"""Scenario checks for confirmed rules; no PostgreSQL substitution."""
from unittest import TestCase
from delivery.domain.aggregates import (
    ContractProductQuantity as Line,
    sum_product_quantities,
    count_selected_targets,
)

class AggregationScenarios(TestCase):
    def test_one_contract_joined_to_three_places_is_not_tripled(self):
        repeated_contract = [Line("contract-1", "C", 10)] * 3
        other_contract = [Line("contract-2", "C", 5)]
        self.assertEqual(sum_product_quantities(repeated_contract + other_contract), {"C": 15})

    def test_two_products_do_not_increase_the_same_customer_count(self):
        lines = [Line("contract-1", "C", 10), Line("contract-1", "BELL", 5)]
        self.assertEqual(sum_product_quantities(lines), {"C": 10, "BELL": 5})
        self.assertEqual(count_selected_targets(["customer-1", "customer-1"]), 1)

    def test_equal_quantities_in_different_contracts_are_both_counted(self):
        self.assertEqual(sum_product_quantities([
            Line("contract-1", "C", 10), Line("contract-2", "C", 10),
        ]), {"C": 20})

    def test_conflicting_copies_of_one_source_are_not_silently_resolved(self):
        with self.assertRaises(ValueError):
            sum_product_quantities([
                Line("contract-1", "C", 10), Line("contract-1", "C", 5),
            ])

class DefaultCountScenarios(TestCase):
    def test_customer_and_two_sites_initially_count_as_one(self):
        from delivery.domain.defaults import initial_count_inclusion
        targets = [
            ("customer-1", "customer"),
            ("site-1", "site"),
            ("site-2", "site"),
        ]
        selected = [identity for identity, kind in targets if initial_count_inclusion(kind)]
        self.assertEqual(count_selected_targets(selected), 1)

    def test_manually_included_sites_count_once_after_additional_contract(self):
        from delivery.domain.defaults import initial_count_inclusion
        selected = ["customer-1"] if initial_count_inclusion("customer") else []
        for identity in ["site-1", "site-2", "site-1"]:
            included_by_planning_team = True
            if included_by_planning_team:
                selected.append(identity)
        self.assertEqual(count_selected_targets(selected), 3)

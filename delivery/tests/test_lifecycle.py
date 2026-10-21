"""Lifecycle business scenarios using immutable in-memory snapshots, not a DB."""
from unittest import TestCase
from delivery.domain.aggregates import ContractProductQuantity as Line
from delivery.domain.lifecycle import ContractSnapshot as Contract, current_customer_quantities

class CurrentPerformanceScenarios(TestCase):
    def test_closed_c_and_live_i_keep_customer_and_only_current_i(self):
        history = (
            Contract("closed-c", "customer-1", False, (Line("closed-c", "C", 10),)),
            Contract("live-i", "customer-1", True, (Line("live-i", "I", 5),)),
        )
        self.assertEqual(current_customer_quantities(history), {"customer-1": {"I": 5}})
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].product_lines[0].quantity, 10)

    def test_same_product_still_live_keeps_marker_and_only_live_quantity(self):
        history = (
            Contract("closed-c", "customer-1", False, (Line("closed-c", "C", 10),)),
            Contract("live-c", "customer-1", True, (Line("live-c", "C", 5),)),
        )
        self.assertEqual(current_customer_quantities(history), {"customer-1": {"C": 5}})

    def test_all_closed_contracts_remove_current_customer_but_not_history(self):
        history = [
            Contract("closed-c", "customer-1", False, (Line("closed-c", "C", 10),)),
            Contract("closed-i", "customer-1", False, (Line("closed-i", "I", 5),)),
        ]
        self.assertEqual(current_customer_quantities(history), {})
        self.assertEqual(len(history), 2)

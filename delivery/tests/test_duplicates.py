"""Manual duplicate-merge decision rules, checked without a database."""
from unittest import TestCase
from delivery.domain.duplicates import ContractMergeDecision, resolve_contract_merge


class ContractMergeDecisionScenarios(TestCase):
    def test_exclude_without_a_surviving_match_is_rejected(self):
        with self.assertRaises(ValueError):
            ContractMergeDecision(contract_id="dup-1", action="exclude")

    def test_include_cannot_also_claim_a_surviving_match(self):
        with self.assertRaises(ValueError):
            ContractMergeDecision(contract_id="dup-1", action="include", superseded_by="primary-1")

    def test_a_contract_cannot_supersede_itself(self):
        with self.assertRaises(ValueError):
            ContractMergeDecision(contract_id="dup-1", action="exclude", superseded_by="dup-1")

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            ContractMergeDecision(contract_id="dup-1", action="delete")


class ResolveContractMergeScenarios(TestCase):
    def test_different_contracts_of_10_and_5_both_stay_included(self):
        decisions = {
            "ten": ContractMergeDecision("ten", "include"),
            "five": ContractMergeDecision("five", "include"),
        }
        resolved = resolve_contract_merge(["ten", "five"], decisions, valid_supersede_target_ids=["primary-existing"])
        self.assertEqual(resolved["ten"].action, "include")
        self.assertEqual(resolved["five"].action, "include")

    def test_a_duplicate_connection_of_the_same_10_unit_contract_is_excluded_not_doubled(self):
        decisions = {"dup-ten": ContractMergeDecision("dup-ten", "exclude", superseded_by="primary-ten")}
        resolved = resolve_contract_merge(["dup-ten"], decisions, valid_supersede_target_ids=["primary-ten"])
        self.assertEqual(resolved["dup-ten"].action, "exclude")
        self.assertEqual(resolved["dup-ten"].superseded_by, "primary-ten")

    def test_every_moving_contract_needs_exactly_one_decision(self):
        with self.assertRaises(ValueError):
            resolve_contract_merge(["ten", "five"], {"ten": ContractMergeDecision("ten", "include")}, valid_supersede_target_ids=[])

    def test_an_extra_decision_for_a_contract_that_is_not_moving_is_rejected(self):
        decisions = {"ten": ContractMergeDecision("ten", "include"), "unrelated": ContractMergeDecision("unrelated", "include")}
        with self.assertRaises(ValueError):
            resolve_contract_merge(["ten"], decisions, valid_supersede_target_ids=[])

    def test_excluded_contract_must_point_to_a_contract_that_survives_the_merge(self):
        decisions = {"dup-ten": ContractMergeDecision("dup-ten", "exclude", superseded_by="gone")}
        with self.assertRaises(ValueError):
            resolve_contract_merge(["dup-ten"], decisions, valid_supersede_target_ids=["primary-ten"])

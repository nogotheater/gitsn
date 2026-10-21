"""Manual duplicate-customer merge decisions only. No automatic duplicate detection.

Callers already restrict inputs to the moving contracts (the duplicate customers'
own contracts) and the set of contracts that can legally survive the merge.
"""
from dataclasses import dataclass

INCLUDE = "include"
EXCLUDE = "exclude"
ACTIONS = (INCLUDE, EXCLUDE)


@dataclass(frozen=True)
class ContractMergeDecision:
    contract_id: str
    action: str
    superseded_by: str = ""

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise ValueError("Each contract needs an explicit include/exclude choice.")
        if self.action == EXCLUDE and not self.superseded_by:
            raise ValueError("A contract marked duplicate needs the surviving contract it matches.")
        if self.action == INCLUDE and self.superseded_by:
            raise ValueError("An included contract does not supersede anything.")
        if self.superseded_by == self.contract_id:
            raise ValueError("A contract cannot supersede itself.")


def resolve_contract_merge(moving_contract_ids, decisions, valid_supersede_target_ids):
    """Confirm every moving contract has exactly one decision and every excluded
    contract's surviving match is part of the contracts that remain after the merge.

    Never sums or moves anything here; callers apply the decisions as one transaction.
    """
    moving_ids = frozenset(moving_contract_ids)
    decided_ids = frozenset(decisions)
    if moving_ids != decided_ids:
        raise ValueError("Every contract being merged needs exactly one decision, no more and no less.")
    valid_targets = frozenset(valid_supersede_target_ids)
    for contract_id, decision in decisions.items():
        if not isinstance(decision, ContractMergeDecision) or decision.contract_id != contract_id:
            raise ValueError("Decision key must match its own contract id.")
        if decision.action == EXCLUDE and decision.superseded_by not in valid_targets:
            raise ValueError("The surviving contract must remain after the merge.")
    return decisions

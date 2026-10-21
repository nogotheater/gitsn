"""DB-independent, confirmed aggregation rules only.

Callers select effective contracts and counted targets using approved business rules.
This module does not decide contract validity, count defaults, or visibility.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from .quantities import positive_quantity

@dataclass(frozen=True)
class ContractProductQuantity:
    contract_id: str
    product_id: str
    quantity: int

    def __post_init__(self):
        object.__setattr__(self, "quantity", positive_quantity(self.quantity))

def sum_product_quantities(lines: Iterable[ContractProductQuantity]) -> dict[str, int]:
    """Deduplicate by contract AND product, never by quantity or installation place."""
    unique_lines: dict[tuple[str, str], int] = {}
    for line in lines:
        key = (line.contract_id, line.product_id)
        if key in unique_lines and unique_lines[key] != line.quantity:
            raise ValueError("Conflicting quantity for one contract/product source.")
        unique_lines[key] = line.quantity
    totals: dict[str, int] = {}
    for (_, product_id), quantity in unique_lines.items():
        totals[product_id] = totals.get(product_id, 0) + quantity
    return totals

def count_selected_targets(selected_target_ids: Iterable[str]) -> int:
    """Input contains only targets explicitly selected for this count."""
    return len(set(selected_target_ids))

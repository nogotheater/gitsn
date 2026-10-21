"""Current performance is computed from active contracts; history is never modified."""
from collections.abc import Iterable
from dataclasses import dataclass
from .aggregates import ContractProductQuantity, sum_product_quantities

@dataclass(frozen=True)
class ContractSnapshot:
    contract_id: str
    customer_id: str
    is_active: bool
    product_lines: tuple[ContractProductQuantity, ...]

    def __post_init__(self):
        if type(self.is_active) is not bool:
            raise ValueError("Contract validity must be an explicit boolean.")
        if any(line.contract_id != self.contract_id for line in self.product_lines):
            raise ValueError("Product line belongs to another contract.")

def current_customer_quantities(contracts: Iterable[ContractSnapshot]) -> dict[str, dict[str, int]]:
    """Keys identify current customers; each value's keys identify current products."""
    lines_by_customer = {}
    source_states = {}
    for contract in contracts:
        state = (contract.customer_id, contract.is_active)
        previous = source_states.setdefault(contract.contract_id, state)
        if previous != state:
            raise ValueError("Conflicting customer or validity for one contract.")
        if contract.is_active:
            lines_by_customer.setdefault(contract.customer_id, []).extend(contract.product_lines)
    return {
        customer_id: sum_product_quantities(lines)
        for customer_id, lines in lines_by_customer.items()
    }

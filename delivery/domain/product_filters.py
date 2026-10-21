"""A current target matches any selected product; empty selection means all."""
from .lifecycle import current_customer_quantities


def products_match_any(current_product_ids, selected_product_ids):
    selected = set(selected_product_ids)
    return not selected or bool(selected.intersection(current_product_ids))


def matching_current_customer_ids(contracts, selected_product_ids):
    selected = frozenset(selected_product_ids)
    return frozenset(
        customer_id
        for customer_id, quantities in current_customer_quantities(contracts).items()
        if products_match_any(quantities, selected)
    )

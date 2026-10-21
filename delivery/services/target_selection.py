"""Internal candidate queries. Audience checks/projection are still required.

All sets share current-contract/product conditions. Never count list rows or
remove hidden/private entries before computing the corresponding count.
"""
from dataclasses import dataclass
from django.db.models import QuerySet
from .current_performance import (
    current_customers_with_any_products,
    current_site_presentations_with_any_products,
)


@dataclass(frozen=True)
class CurrentTargetQueries:
    listed_customers: QuerySet
    counted_customers: QuerySet
    listed_sites: QuerySet
    counted_sites: QuerySet


def current_target_queries(selected_product_ids=()):
    selected = frozenset(selected_product_ids)
    customers = current_customers_with_any_products(selected)
    sites = current_site_presentations_with_any_products(selected)
    return CurrentTargetQueries(
        listed_customers=customers.filter(show_in_list=True),
        counted_customers=customers.filter(include_in_total=True),
        listed_sites=sites.filter(show_in_list=True),
        counted_sites=sites.filter(include_in_total=True),
    )

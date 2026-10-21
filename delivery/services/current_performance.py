"""Internal ORM reads only; callers must enforce audience and filter policy.

Current quantities/products exclude inactive contracts. Contract history remains intact.
PostgreSQL integration verification is still pending.
"""
from django.db.models import F
from delivery.models import Contract, ContractProduct, ContractSite, Customer, SitePresentation, SiteProductSelection
from delivery.domain.aggregates import ContractProductQuantity, sum_product_quantities

def customer_has_current_contract(customer_id):
    return Contract.objects.filter(customer_id=customer_id, is_active=True).exists()

def customer_current_quantities(customer_id):
    rows = ContractProduct.objects.filter(
        contract__customer_id=customer_id,
        contract__is_active=True,
    ).values_list("contract_id", "product_id", "quantity")
    return sum_product_quantities(
        ContractProductQuantity(str(contract_id), str(product_id), quantity)
        for contract_id, product_id, quantity in rows
    )

def site_has_current_contract(site_id):
    return ContractSite.objects.filter(
        site_id=site_id, contract__is_active=True,
    ).exists()

def site_current_product_ids(site_id):
    return SiteProductSelection.objects.filter(
        contract_site__site_id=site_id,
        contract_site__contract__is_active=True,
        contract_product__contract_id=F("contract_site__contract_id"),
    ).values_list("contract_product__product_id", flat=True).distinct()


def current_customers_with_any_products(selected_product_ids):
    """Internal query; apply count inclusion, classification and audience before output.

    Products may come from different active contracts of this same customer.
    One selected product is enough. Repeated products never duplicate a customer.
    """
    selected = frozenset(selected_product_ids)
    customers = Customer.objects.filter(contracts__is_active=True).distinct()
    if not selected:
        return customers
    matching = (
        ContractProduct.objects.filter(contract__is_active=True, product_id__in=selected)
        .order_by().values("contract__customer_id")
    )
    return customers.filter(pk__in=matching)


def current_site_presentations_with_any_products(selected_product_ids):
    """Match products actually assigned to each place, never another place's products."""
    selected = frozenset(selected_product_ids)
    presentations = SitePresentation.objects.filter(
        site__contract_links__contract__is_active=True,
    ).distinct()
    if not selected:
        return presentations
    matching = (
        SiteProductSelection.objects.filter(
            contract_site__contract__is_active=True,
            contract_product__contract_id=F("contract_site__contract_id"),
            contract_product__product_id__in=selected,
        )
        .order_by().values("contract_site__site_id")
    )
    return presentations.filter(site_id__in=matching)

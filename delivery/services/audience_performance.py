"""Shared summary data for future HTML and PDF adapters; no routes added here.

Private targets contribute only numeric aggregates for partners. Their names,
logo paths and product badges are not fetched for the returned partner list.
"""
from collections import defaultdict
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from delivery.domain.audience import ProductBadge, TargetRecord, project_targets
from delivery.models import (
    Category, Contract, ContractProduct, Customer, SitePresentation,
    SiteProductSelection, UserAccessProfile,
)
from .access import audience_for_user, require_manager
from .current_performance import (
    current_customers_with_any_products, current_site_presentations_with_any_products,
)


def _badge(row):
    return ProductBadge(str(row['product_id']), row['product_name'], row['marker'], row['color'])


def current_performance_payload(user, *, selected_product_ids=(), categories=(), visibility='all', include_badges=True):
    """Any selected product and any selected category match (both OR); empty means no restriction."""
    audience = audience_for_user(user)
    try:
        selected = frozenset(UUID(str(value)) for value in selected_product_ids)
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({'products': 'Invalid product selection.'}) from None
    chosen_categories = frozenset(categories)
    if not chosen_categories <= frozenset(Category.values):
        raise ValidationError({'category': 'Invalid customer category.'})
    if visibility not in {'all', 'public', 'private'}:
        raise ValidationError({'visibility': 'Invalid visibility selection.'})

    customers = current_customers_with_any_products(selected)
    sites = current_site_presentations_with_any_products(selected)
    filters = {}
    if visibility != 'all':
        filters['partner_public'] = visibility == 'public'
    if chosen_categories:
        filters['category__in'] = sorted(chosen_categories)
    candidates = Q(show_in_list=True) | Q(include_in_total=True)
    columns = ('id', 'category', 'region', 'show_in_list', 'include_in_total', 'partner_public', 'display_as')
    customer_rows = list(customers.filter(candidates, **filters).values(*columns))
    site_rows = list(sites.filter(candidates, **filters).values(*columns))
    visible = lambda row: row['show_in_list'] and (
        audience == UserAccessProfile.Audience.EMPLOYEE or row['partner_public'])
    customer_ids = [row['id'] for row in customer_rows if visible(row)]
    site_ids = [row['id'] for row in site_rows if visible(row)]
    customer_metadata = {
        row['id']: (row['organization__official_name'], bool(row['logo']))
        for row in Customer.objects.filter(pk__in=customer_ids).values('id', 'organization__official_name', 'logo')
    }
    site_metadata = {
        row['id']: (row['site__official_name'], bool(row['logo']))
        for row in SitePresentation.objects.filter(pk__in=site_ids).values('id', 'site__official_name', 'logo')
    }
    customer_badges = defaultdict(dict)
    for row in (ContractProduct.objects.filter(
        contract__is_active=True, contract__customer_id__in=customer_ids,
    ).values('product_id', target_id=F('contract__customer_id'), product_name=F('product__name'),
             marker=F('product__marker'), color=F('product__color')) if include_badges else []):
        customer_badges[row['target_id']][row['product_id']] = _badge(row)
    site_badges = defaultdict(dict)
    for row in (SiteProductSelection.objects.filter(
        contract_site__contract__is_active=True,
        contract_product__contract_id=F('contract_site__contract_id'),
        contract_site__site__presentation__id__in=site_ids,
    ).values(product_id=F('contract_product__product_id'),
             target_id=F('contract_site__site__presentation__id'),
             product_name=F('contract_product__product__name'),
             marker=F('contract_product__product__marker'),
             color=F('contract_product__product__color')) if include_badges else []):
        site_badges[row['target_id']][row['product_id']] = _badge(row)

    records = []
    for kind, rows, metadata, badges in (
        ('customer', customer_rows, customer_metadata, customer_badges),
        ('site', site_rows, site_metadata, site_badges),
    ):
        for row in rows:
            name, has_logo = metadata.get(row['id'], ('', False))
            products = tuple(sorted(badges[row['id']].values(), key=lambda badge: badge.id))
            records.append(TargetRecord(
                **{**row, 'id': str(row['id'])}, kind=kind, name=name,
                has_logo=has_logo, products=products,
            ))
    return project_targets(records, audience=audience, category_codes=Category.values)


def contract_source_metadata(user, contract_id):
    require_manager(user)
    return Contract.objects.values(
        'source_email_subject', 'source_email_received_on', 'source_email_sender',
    ).get(pk=contract_id)

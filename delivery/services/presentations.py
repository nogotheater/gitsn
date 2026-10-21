"""Construct unsaved entries using only confirmed registration defaults."""
from delivery.models import Category, Customer, SitePresentation

def initial_partner_visibility(category):
    if category not in Category.values:
        raise ValueError("고객 분류를 선택해 주세요.")
    return category != Category.PRIVATE

def new_customer(*, organization, category, region="", partner_public=None, **fields):
    if partner_public is None:
        partner_public = initial_partner_visibility(category)
    return Customer(organization=organization, category=category, region=region,
                    partner_public=partner_public, **fields)

def new_site_presentation(*, site, category, region="", partner_public=None, **fields):
    if partner_public is None:
        partner_public = initial_partner_visibility(category)
    return SitePresentation(site=site, category=category, region=region,
                            partner_public=partner_public, **fields)

def change_category(presentation, category):
    presentation.partner_public = initial_partner_visibility(category)
    presentation.category = category
    return presentation

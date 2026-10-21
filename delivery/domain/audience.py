"""Whitelisted output from already-current, already-filtered target records."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductBadge:
    id: str
    name: str
    marker: str
    color: str


@dataclass(frozen=True)
class TargetRecord:
    id: str
    kind: str
    category: str
    region: str
    show_in_list: bool
    include_in_total: bool
    partner_public: bool
    name: str = ''
    has_logo: bool = False
    products: tuple[ProductBadge, ...] = ()
    display_as: str = ''


def project_targets(records, *, audience, category_codes=()):
    if audience not in {'employee', 'partner'}:
        raise ValueError('Unknown audience.')
    unique = {}
    for record in records:
        key = (record.kind, record.id)
        if record.kind not in {'customer', 'site'}:
            raise ValueError('Unknown target kind.')
        if record.display_as not in {'', 'customer', 'site'}:
            raise ValueError('Unknown display kind.')
        if any(type(value) is not bool for value in
               (record.show_in_list, record.include_in_total, record.partner_public)):
            raise ValueError('Explicit target settings required.')
        if key in unique and unique[key] != record:
            raise ValueError('Conflicting target records.')
        unique[key] = record

    total = public_count = private_count = 0
    by_category = dict.fromkeys(category_codes, 0)
    private_by_category = dict.fromkeys(category_codes, 0)
    items = []
    for record in unique.values():
        if record.include_in_total:
            total += 1
            by_category[record.category] = by_category.get(record.category, 0) + 1
            if record.partner_public:
                public_count += 1
            else:
                private_count += 1
                private_by_category[record.category] = private_by_category.get(record.category, 0) + 1
        if not record.show_in_list or (audience == 'partner' and not record.partner_public):
            continue
        items.append({
            'id': record.id, 'kind': record.kind, 'name': record.name,
            'display_as': record.display_as or record.kind,
            'category': record.category, 'region': record.region,
            'has_logo': record.has_logo,
            'products': [
                {'id': badge.id, 'name': badge.name, 'marker': badge.marker, 'color': badge.color}
                for badge in record.products
            ],
        })
    return {'items': items, 'counts': {
        'total': total, 'public': public_count, 'private': private_count,
        'by_category': by_category, 'private_by_category': private_by_category,
    }}

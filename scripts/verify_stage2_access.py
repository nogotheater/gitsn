"""Local DB integration for shared audience services. All fixture writes roll back.

No HTTP/login/PDF feature is exercised; those routes are future-stage work.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

root = Path('/app') if Path('/app/manage.py').is_file() else Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from delivery.models import (
    Category, Contract, ContractProduct, ContractSite, Customer, InstallationSite,
    Organization, Product, Region, SitePresentation, SiteProductSelection, UserAccessProfile,
)
from delivery.services.access import require_employee, require_manager
from delivery.services.audience_performance import current_performance_payload, contract_source_metadata
from delivery.services.presentations import new_customer, new_site_presentation


def check(label, condition):
    if not condition:
        raise RuntimeError(label)
    print('PASS: ' + label, flush=True)


def denied(label, action):
    try:
        action()
    except PermissionDenied:
        check(label, True)
    else:
        raise RuntimeError(label + ' was allowed.')


def run():
    if not settings.DEBUG or connection.vendor != 'postgresql':
        raise RuntimeError('Local DEBUG PostgreSQL environment required.')
    prefix = 'ACCESS_VERIFY_' + uuid4().hex
    created = defaultdict(list)

    def keep(obj):
        obj.save()
        created[type(obj)].append(obj.pk)
        return obj

    User = get_user_model()
    with transaction.atomic():
        if Customer.objects.exists() or SitePresentation.objects.exists():
            raise RuntimeError('Run this diagnostic before importing real customer data.')
        users = {}
        for role in ['employee', 'partner', 'manager', 'inactive', 'no_profile']:
            user = User(username=prefix + '_' + role, is_active=role != 'inactive')
            user.set_unusable_password()
            keep(user)
            if role != 'no_profile':
                keep(UserAccessProfile(user=user, audience='partner' if role == 'partner' else 'employee'))
            users[role] = user
        permission = Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery')
        users['manager'].user_permissions.add(permission)
        users['partner'].user_permissions.add(permission)
        employee, partner, manager = users['employee'], users['partner'], users['manager']
        c = keep(Product(code=prefix + '_C', name='Access verification C', marker='C'))
        i = keep(Product(code=prefix + '_I', name='Access verification I', marker='I'))
        private_product = keep(Product(code=prefix + '_SECRET', name=prefix + '_SECRET_PRODUCT', marker='X'))
        customers, contracts, lines = [], [], []
        for index in range(100):
            public = index < 70
            org = keep(Organization(official_name=prefix + ('_PUBLIC_' if public else '_SECRET_') + str(index)))
            category = Category.PUBLIC if public else Category.PRIVATE
            customer = keep(new_customer(organization=org, category=category,
                                         memo=prefix + '_SECRET_MEMO' if not public else '',
                                         logo='logos/' + prefix + '_SECRET.png' if not public else ''))
            contract = keep(Contract(contracting_party=org, customer=customer, is_active=True,
                                     source_email_subject=prefix + '_MAIL', source_email_sender=prefix + '_SENDER'))
            c_line = keep(ContractProduct(contract=contract, product=c, quantity=1))
            if index < 10 or 70 <= index < 75:
                keep(ContractProduct(contract=contract, product=i, quantity=2))
            if index == 70:
                keep(ContractProduct(contract=contract, product=private_product, quantity=1))
            customers.append(customer)
            contracts.append(contract)
            lines.append(c_line)

        staff = current_performance_payload(employee)
        external = current_performance_payload(partner)
        check('70 public and 30 private produce the same total 100',
              staff['counts'] == external['counts'] and external['counts']['total'] == 100 and
              external['counts']['public'] == 70 and external['counts']['private'] == 30 and
              len(staff['items']) == 100 and len(external['items']) == 70)
        wire = json.dumps(external, ensure_ascii=True)
        secret_tokens = [prefix + '_SECRET', prefix + '_MAIL', prefix + '_SENDER']
        secret_tokens += [str(customer.pk) for customer in customers[70:]] + [str(private_product.pk)]
        check('Partner payload contains no private identity logo product memo or source',
              not any(token in wire for token in secret_tokens))
        both_staff = current_performance_payload(employee, selected_product_ids=[c.pk, i.pk])
        both_partner = current_performance_payload(partner, selected_product_ids=[c.pk, i.pk])
        check('C or I search returns total 100 with private count 30 for both audiences',
              both_staff['counts'] == both_partner['counts'] and both_partner['counts']['total'] == 100 and
              both_partner['counts']['private'] == 30 and len(both_partner['items']) == 70)
        private = current_performance_payload(partner, category=Category.PRIVATE, selected_product_ids=[c.pk, i.pk])
        check('Private category filter returns count only', private['items'] == [] and private['counts']['total'] == 30)
        unknown = current_performance_payload(partner, selected_product_ids=[uuid4()])
        check('Unmatched product returns zero and empty list', unknown['counts']['total'] == 0 and unknown['items'] == [])
        customers[0].category = Category.LOCAL
        customers[0].region = Region.CAPITAL
        customers[0].save(update_fields=['category', 'region'])
        local_staff = current_performance_payload(employee, category=Category.LOCAL, region=Region.CAPITAL)
        local_partner = current_performance_payload(partner, category=Category.LOCAL, region=Region.CAPITAL)
        check('Category and region filters use identical audience counts',
              local_staff['counts'] == local_partner['counts'] and local_partner['counts']['total'] == 1)

        # A counted private place contributes a number but never an individual row.
        site = keep(InstallationSite(official_name=prefix + '_SECRET_SITE'))
        presentation = keep(new_site_presentation(site=site, category=Category.PRIVATE, include_in_total=True))
        link = keep(ContractSite(contract=contracts[70], site=site))
        keep(SiteProductSelection(contract_site=link, contract_product=lines[70]))
        staff = current_performance_payload(employee)
        external = current_performance_payload(partner)
        check('Exceptional private place adds one to both totals without disclosure',
              staff['counts'] == external['counts'] and external['counts']['total'] == 101 and
              external['counts']['private'] == 31 and prefix + '_SECRET_SITE' not in json.dumps(external))
        external_c = current_performance_payload(partner, selected_product_ids=[c.pk])
        check('Place badges use only their assigned contract products',
              external_c['counts']['total'] == 101 and
              current_performance_payload(partner, selected_product_ids=[c.pk, i.pk])['counts']['total'] == 101 and
              current_performance_payload(partner, selected_product_ids=[i.pk])['counts']['total'] == 15)

        denied('Anonymous list access blocked', lambda: current_performance_payload(AnonymousUser()))
        denied('Inactive user blocked', lambda: current_performance_payload(users['inactive']))
        denied('Missing role profile blocked', lambda: current_performance_payload(users['no_profile']))
        denied('Partner employee-detail access blocked', lambda: require_employee(partner))
        denied('Partner manager permission does not grant employee access', lambda: require_manager(partner))
        denied('Ordinary employee cannot manage data', lambda: require_manager(employee))
        denied('Ordinary employee cannot read source metadata', lambda: contract_source_metadata(employee, contracts[0].pk))
        denied('Partner cannot read source metadata', lambda: contract_source_metadata(partner, contracts[0].pk))
        source = contract_source_metadata(manager, contracts[0].pk)
        check('Planning manager can read source metadata', source['source_email_subject'] == prefix + '_MAIL')
        try:
            current_performance_payload(partner, category='not-a-category')
        except ValidationError:
            check('Invalid filter rejected', True)
        else:
            raise RuntimeError('Invalid filter accepted.')
        contracts[70].is_active = False
        contracts[70].save(update_fields=['is_active'])
        staff = current_performance_payload(employee)
        external = current_performance_payload(partner)
        check('Closed private contract removes its customer and exceptional place from both counts',
              staff['counts'] == external['counts'] and external['counts']['total'] == 99 and
              external['counts']['private'] == 29)
        transaction.set_rollback(True)

    check('Temporary accounts and customer data rolled back',
          not any(model.objects.filter(pk__in=ids).exists() for model, ids in created.items()))
    print('STAGE2_ACCESS_CHECKS_OK', flush=True)
    print('Future HTML, login, protected logo and PDF routes require separate checks.', flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('STAGE2_ACCESS_CHECKS_FAILED: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)

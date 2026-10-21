"""Local PostgreSQL business scenarios; every created row is rolled back.

May be piped to the existing web container without rebuilding it.
This checks data rules, not audience authorization, PDF, or restart durability.
"""
import os
import sys
from pathlib import Path
from uuid import uuid4

project = Path('/app') if Path('/app/manage.py').is_file() else Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from delivery.models import (
    Category, Contract, ContractProduct, ContractSite, Customer,
    InstallationSite, Organization, Product, SitePresentation, SiteProductSelection,
)
from delivery.services.current_performance import (
    customer_current_quantities, customer_has_current_contract,
    current_customers_with_any_products, current_site_presentations_with_any_products,
    site_current_product_ids,
)
from delivery.services.presentations import new_customer, new_site_presentation, change_category
from delivery.services.target_selection import current_target_queries


def check(name, condition):
    if not condition:
        raise RuntimeError(name)
    print('PASS: ' + name, flush=True)


def run():
    if not settings.DEBUG or connection.vendor != 'postgresql':
        raise RuntimeError('Local DEBUG PostgreSQL environment required.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version_num')")
        check('PostgreSQL 17', int(cursor.fetchone()[0]) // 10000 == 17)
    required = {
        ('delivery', '0001_initial'),
        ('delivery', '0002_contract_email_metadata'),
        ('delivery', '0003_independent_list_visibility'),
    }
    check('Delivery migrations applied', required <= set(MigrationRecorder(connection).applied_migrations()))
    created = []
    prefix = 'VERIFY_' + uuid4().hex

    def keep(obj):
        obj.save()
        created.append((type(obj), obj.pk))
        return obj

    with transaction.atomic():
        party = keep(Organization(official_name=prefix))
        customer = keep(new_customer(organization=party, category=Category.PUBLIC))
        product_c = keep(Product(code=prefix + '_C', name='Verification C', marker='C'))
        product_i = keep(Product(code=prefix + '_I', name='Verification I', marker='I'))
        first = keep(Contract(contracting_party=party, customer=customer, is_active=True))
        second = keep(Contract(contracting_party=party, customer=customer, is_active=True))
        third = keep(Contract(contracting_party=party, customer=customer, is_active=True))
        line_c10 = keep(ContractProduct(contract=first, product=product_c, quantity=10))
        keep(ContractProduct(contract=second, product=product_c, quantity=5))
        line_i = keep(ContractProduct(contract=third, product=product_i, quantity=5))
        first.refresh_from_db()
        check('Optional email fields save empty', first.source_email_subject == '' and
              first.source_email_sender == '' and first.source_email_received_on is None)

        site_a = keep(InstallationSite(official_name=prefix + '_A'))
        site_b = keep(InstallationSite(official_name=prefix + '_B'))
        presentation_a = keep(new_site_presentation(site=site_a, category=Category.PUBLIC))
        presentation_b = keep(new_site_presentation(site=site_b, category=Category.PUBLIC))
        link_a = keep(ContractSite(contract=first, site=site_a))
        link_b = keep(ContractSite(contract=first, site=site_b))
        keep(SiteProductSelection(contract_site=link_a, contract_product=line_c10))
        keep(SiteProductSelection(contract_site=link_b, contract_product=line_c10))
        quantities = customer_current_quantities(customer.pk)
        check('10 plus 5 equals 15 despite two installation places',
              quantities == {str(product_c.pk): 15, str(product_i.pk): 5})
        selected = [product_c.pk, product_i.pk]
        check('Customer matches selected products across active contracts',
              current_customers_with_any_products(selected).filter(pk=customer.pk).count() == 1)
        check('Place displays only its assigned C product',
              set(site_current_product_ids(site_a.pk)) == {product_c.pk} and
              current_site_presentations_with_any_products(selected).filter(pk=presentation_a.pk).exists())

        # Each one-product customer independently matches the any-selected rule.
        for product in (product_c, product_i):
            org = keep(Organization(official_name=prefix + '_' + product.marker))
            single = keep(new_customer(organization=org, category=Category.PUBLIC))
            contract = keep(Contract(contracting_party=org, customer=single, is_active=True))
            keep(ContractProduct(contract=contract, product=product, quantity=1))
            check('One-product customer included: ' + product.marker,
                  current_customers_with_any_products(selected).filter(pk=single.pk).exists())

        def own_counts():
            q = current_target_queries([])
            place_ids = [presentation_a.pk, presentation_b.pk]
            listed = q.listed_customers.filter(pk=customer.pk).count() + q.listed_sites.filter(pk__in=place_ids).count()
            counted = q.counted_customers.filter(pk=customer.pk).count() + q.counted_sites.filter(pk__in=place_ids).count()
            return listed, counted

        check('City and two places listed but only city counted', own_counts() == (3, 1))
        presentation_a.include_in_total = True
        presentation_a.save(update_fields=['include_in_total'])
        check('Exceptional place adds one count without another list row', own_counts() == (3, 2))
        presentation_a.show_in_list = False
        presentation_a.save(update_fields=['show_in_list'])
        check('Hiding place does not remove its count', own_counts() == (2, 2))

        change_category(customer, Category.PRIVATE).save(update_fields=['category', 'partner_public'])
        customer.refresh_from_db()
        check('Category change resets partner visibility only',
              not customer.partner_public and customer.include_in_total and customer.show_in_list)

        try:
            with transaction.atomic():
                ContractProduct.objects.create(contract=first, product=product_c, quantity=1)
        except IntegrityError:
            check('DB rejects duplicate contract product', True)
        else:
            raise RuntimeError('Duplicate contract product was accepted.')

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE delivery_contractproduct SET quantity = 0 WHERE id = %s', [line_c10.pk])
        except IntegrityError:
            check('DB rejects zero quantity', True)
        else:
            raise RuntimeError('DB accepted zero quantity.')

        try:
            SiteProductSelection(contract_site=link_a, contract_product=line_i).save()
        except ValidationError:
            check('Cross-contract site product rejected', True)
        else:
            raise RuntimeError('Cross-contract site product was accepted.')

        first.is_active = False
        first.save(update_fields=['is_active'])
        check('Partial termination keeps customer and remaining quantities',
              customer_has_current_contract(customer.pk) and
              customer_current_quantities(customer.pk) == {str(product_c.pk): 5, str(product_i.pk): 5})
        second.is_active = False
        second.save(update_fields=['is_active'])
        check('Remaining I still matches C or I; ended C alone no longer matches',
              customer_has_current_contract(customer.pk) and
              current_customers_with_any_products(selected).filter(pk=customer.pk).exists() and
              not current_customers_with_any_products([product_c.pk]).filter(pk=customer.pk).exists())
        third.is_active = False
        third.save(update_fields=['is_active'])
        line_c10.refresh_from_db()
        check('All terminated: current count removed, original history retained',
              own_counts() == (0, 0) and customer_current_quantities(customer.pk) == {} and
              Contract.objects.filter(customer=customer).count() == 3 and line_c10.quantity == 10)
        transaction.set_rollback(True)

    check('All verification records rolled back',
          not any(model.objects.filter(pk=pk).exists() for model, pk in created))
    print('STAGE2_DATA_CHECKS_OK', flush=True)
    print('Audience authorization and restart durability still need separate checks.', flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('STAGE2_DATA_CHECKS_FAILED: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)

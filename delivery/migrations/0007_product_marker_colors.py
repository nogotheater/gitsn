from django.db import migrations


def match_s_color(apps, schema_editor):
    """2026-10-22 형우: 마킹에서 B(Alpha-B)·D(Smart-D)는 S(Alpha-S)와 같은 색. 이후 색은 제품 관리 화면에서 바꿀 수 있다."""
    Product = apps.get_model('delivery', 'Product')
    source = Product.objects.filter(marker__iexact='S').exclude(color='').order_by('created_at', 'pk').first()
    if source is None:
        return
    for marker in ('B', 'D'):
        for product in Product.objects.filter(marker__iexact=marker):
            product.color = source.color
            product.save(update_fields=['color', 'updated_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('delivery', '0006_customer_location'),
    ]

    operations = [
        migrations.RunPython(match_s_color, migrations.RunPython.noop),
    ]

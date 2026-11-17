from django.db import migrations, models


def keep_existing_logos(apps, schema_editor):
    """2026-11-17 형우: 지금 올라가 있는 심볼은 보기 좋다 → 모양은 그대로(as_is). 새로 올리는 심볼부터 자동 정리."""
    for name in ('Customer', 'SitePresentation'):
        model = apps.get_model('delivery', name)
        model.objects.exclude(logo='').update(logo_fit='as_is')


FIT = [('auto', '자동 정리'), ('as_is', '올린 그대로')]
SIZE = [('small', '작게'), ('normal', '보통'), ('large', '크게')]
BACKGROUND = [('remove', '흰 배경 지우기'), ('keep', '배경 유지')]


class Migration(migrations.Migration):
    dependencies = [('delivery', '0008_logo_rendition')]

    operations = [
        *[op for model in ('customer', 'sitepresentation') for op in (
            migrations.AddField(model_name=model, name='logo_fit', field=models.CharField('심볼 정리', max_length=8, choices=FIT, default='auto')),
            migrations.AddField(model_name=model, name='logo_size', field=models.CharField('심볼 크기', max_length=8, choices=SIZE, default='normal')),
            migrations.AddField(model_name=model, name='logo_background', field=models.CharField('심볼 배경', max_length=8, choices=BACKGROUND, default='remove')),
        )],
        migrations.AddField(model_name='logorendition', name='info', field=models.JSONField(blank=True, default=dict)),
        migrations.RunPython(keep_existing_logos, migrations.RunPython.noop),
    ]

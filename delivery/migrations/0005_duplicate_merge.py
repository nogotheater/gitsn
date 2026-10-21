from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0004_presentation_display_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='merged_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='통합된 일시'),
        ),
        migrations.AddField(
            model_name='customer',
            name='merged_into',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='merged_duplicates', to='delivery.customer'),
        ),
        migrations.AddField(
            model_name='contract',
            name='superseded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supersedes', to='delivery.contract'),
        ),
    ]

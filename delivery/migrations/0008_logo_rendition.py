from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('delivery', '0007_product_marker_colors')]

    operations = [
        migrations.CreateModel(
            name='LogoRendition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=16)),
                ('object_id', models.UUIDField()),
                ('source', models.CharField(max_length=255)),
                ('web', models.BinaryField(blank=True, default=b'')),
                ('print_png', models.BinaryField(blank=True, default=b'')),
                ('created_at', models.DateTimeField(auto_now=True)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('kind', 'object_id'), name='logo_rendition_target')]},
        ),
    ]

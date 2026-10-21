from django.db import migrations, models


class Migration(migrations.Migration):
    """8단계 지역 현황 지도: 고객사 소재지와 기관 유형(모두 선택 입력, 기존 행은 빈 값)."""

    dependencies = [
        ('delivery', '0005_duplicate_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='location_code',
            field=models.CharField(blank=True, max_length=5, verbose_name='소재지'),
        ),
        migrations.AddField(
            model_name='customer',
            name='institution_type',
            field=models.CharField(blank=True, choices=[('admin', '행정기관'), ('facility', '시설·공기업')], max_length=16, verbose_name='기관 유형'),
        ),
    ]

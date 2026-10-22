"""고객사 삭제(4단계에 추가, 2026-10-22 형우 확정).

계약이 있어도 지울 수 있고, 확인 화면을 한 번 거친다. 되돌릴 수 없다.
지우는 것:
- 고객사와 그 고객사의 모든 계약(유효·종료), 계약 제품, 설치 장소 연결, 장소별 제품
- 이 고객사로 통합된 중복 고객사(merged_into)
- 이 계약들에만 쓰인 설치 장소와 그 표시 설정
- 더 이상 어디에도 쓰이지 않는 기관(고객사 기관·계약 상대 기관)과 심볼 파일
남기는 것: 다른 계약에도 쓰이는 설치 장소·계약 상대 기관, 제품 목록.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from delivery.models import (
    Contract, ContractProduct, ContractSite, Customer, InstallationSite, Organization,
    SitePresentation, SiteProductSelection,
)
from .access import require_manager


def _family(customer):
    """고객사 + 그 고객사로 통합된 중복 고객사(여러 단계까지). 부모가 앞에 온다."""
    family, queue = [], [customer]
    while queue:
        current = queue.pop(0)
        family.append(current)
        queue.extend(current.merged_duplicates.select_related('organization'))
    return family


def deletion_plan(customer):
    family = _family(customer)
    contracts = list(Contract.objects.filter(customer__in=family).select_related('contracting_party'))
    contract_ids = [c.pk for c in contracts]
    sites = list(InstallationSite.objects.filter(contract_links__contract_id__in=contract_ids).distinct())
    only_here = [s for s in sites if not s.contract_links.exclude(contract_id__in=contract_ids).exists()]
    return {
        'customer': customer, 'duplicates': family[1:], 'family': family,
        'contracts': contracts, 'active_count': sum(1 for c in contracts if c.is_active),
        'ended_count': sum(1 for c in contracts if not c.is_active),
        'sites_deleted': only_here, 'sites_kept': len(sites) - len(only_here),
    }


def delete_customer(user, customer_id):
    require_manager(user)
    with transaction.atomic():
        customer = Customer.objects.select_for_update().select_related('organization').get(pk=customer_id)
        plan = deletion_plan(customer)
        contract_ids = [c.pk for c in plan['contracts']]
        if Contract.objects.filter(superseded_by_id__in=contract_ids).exclude(pk__in=contract_ids).exists():
            raise ValidationError('다른 고객사의 계약이 이 고객사의 계약을 기준으로 중복 제외되어 있어 삭제할 수 없습니다. 기획팀에 알려 주세요.')
        org_ids = {c.organization_id for c in plan['family']} | {c.contracting_party_id for c in plan['contracts']}
        site_ids = [s.pk for s in plan['sites_deleted']]
        logos = [c.logo for c in plan['family'] if c.logo]
        logos += [p.logo for p in SitePresentation.objects.filter(site_id__in=site_ids) if p.logo]

        SiteProductSelection.objects.filter(contract_site__contract_id__in=contract_ids).delete()
        ContractSite.objects.filter(contract_id__in=contract_ids).delete()
        ContractProduct.objects.filter(contract_id__in=contract_ids).delete()
        Contract.objects.filter(pk__in=contract_ids).update(superseded_by=None)
        Contract.objects.filter(pk__in=contract_ids).delete()
        SitePresentation.objects.filter(site_id__in=site_ids).delete()
        InstallationSite.objects.filter(pk__in=site_ids).delete()
        for member in reversed(plan['family']):  # 통합된 쪽부터(merged_into 보호)
            member.delete()
        for org_id in org_ids:
            if not Customer.objects.filter(organization_id=org_id).exists() and not Contract.objects.filter(contracting_party_id=org_id).exists():
                Organization.objects.filter(pk=org_id).delete()

        def retire(files=tuple((f.storage, f.name) for f in logos)):
            for storage, name in files:
                if not Customer.objects.filter(logo=name).exists() and not SitePresentation.objects.filter(logo=name).exists():
                    storage.delete(name)
        transaction.on_commit(retire)
        return {'name': str(customer), 'contracts': len(contract_ids), 'duplicates': len(plan['duplicates'])}

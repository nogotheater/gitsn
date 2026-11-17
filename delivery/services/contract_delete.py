"""잘못 넣은 계약 삭제(2026-11-17 형우).

영천시 환경사업소 계약을 영천시 고객사에 넣었다가, 환경사업소가 직접 계약한 기관이라 새 고객사로 다시 넣기로 했다
("그냥 새로 고객사를 추가하는게 제일 깔끔"). '계약 종료'는 실제로 끝난 계약을 과거 기록으로 남기는 것이라,
잘못 넣은 계약을 지우는 기능이 따로 필요하다.

지우는 것: 계약, 계약 제품, 설치 장소 연결·장소별 제품, 다른 계약에 안 쓰이는 설치 장소(와 그 표시 설정·심볼).
지우지 않는 것: 고객사, 계약 당사자 기관, 다른 계약. 중복 통합 기록과 묶인 계약은 지우지 않는다.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from delivery.models import Contract, ContractProduct, ContractSite, Customer, InstallationSite, Organization, SitePresentation, SiteProductSelection
from .access import require_manager


def contract_deletion_plan(contract):
    sites = list(InstallationSite.objects.filter(contract_links__contract=contract).distinct())
    only_here = [site for site in sites if not site.contract_links.exclude(contract=contract).exists()]
    blockers = []
    if contract.superseded_by_id or contract.supersedes.exists():
        blockers.append('중복 통합 기록과 묶인 계약이라 지울 수 없습니다.')
    return {'contract': contract, 'lines': list(contract.product_lines.select_related('product')),
            'sites_deleted': only_here, 'sites_kept': [site for site in sites if site not in only_here], 'blockers': blockers}


def delete_contract(user, contract_id, revision):
    require_manager(user)
    with transaction.atomic():
        contract = Contract.objects.select_for_update().select_related('customer__organization').get(pk=contract_id)
        if not revision or revision != contract.updated_at.isoformat():
            raise ValidationError('다른 작업에서 계약이 수정되었습니다. 새로고침해 최신 내용을 확인한 뒤 다시 시도해 주세요.')
        plan = contract_deletion_plan(contract)
        if plan['blockers']:
            raise ValidationError(plan['blockers'])
        site_ids = [site.pk for site in plan['sites_deleted']]
        logos = [p.logo for p in SitePresentation.objects.filter(site_id__in=site_ids) if p.logo]
        party_id, customer = contract.contracting_party_id, contract.customer
        SiteProductSelection.objects.filter(contract_site__contract=contract).delete()
        ContractSite.objects.filter(contract=contract).delete()
        ContractProduct.objects.filter(contract=contract).delete()
        contract.delete()
        SitePresentation.objects.filter(site_id__in=site_ids).delete()
        InstallationSite.objects.filter(pk__in=site_ids).delete()
        if not Customer.objects.filter(organization_id=party_id).exists() and not Contract.objects.filter(contracting_party_id=party_id).exists():
            Organization.objects.filter(pk=party_id).delete()   # 이 계약에만 쓰인 '다른 기관' 계약 당사자
        customer.save(update_fields=['updated_at'])              # 납품현황이 바로 새로 그려지게(자료 판 번호)

        def retire(files=tuple((f.storage, f.name) for f in logos)):
            for storage, name in files:
                if not Customer.objects.filter(logo=name).exists() and not SitePresentation.objects.filter(logo=name).exists():
                    storage.delete(name)
        transaction.on_commit(retire)
        return customer

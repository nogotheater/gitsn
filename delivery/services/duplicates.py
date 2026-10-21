"""Manual duplicate-customer consolidation (stage 6). No automatic duplicate detection."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from delivery.domain.duplicates import resolve_contract_merge
from delivery.models import Contract, Customer
from .access import require_manager
from .planning import save_presentation


def duplicate_candidates(primary, query):
    """Customers that can still be chosen as a duplicate of ``primary``."""
    results = Customer.objects.select_related('organization').filter(merged_into__isnull=True).exclude(pk=primary.pk)
    if query:
        results = results.filter(organization__official_name__icontains=query)
    return results.order_by('organization__official_name')


def merge_duplicate_customers(user, primary_id, duplicate_ids, presentation_data, contract_decisions):
    """Apply one manual duplicate-customer merge as a single DB transaction.

    ``contract_decisions`` maps each moving contract's id (str) to a
    delivery.domain.duplicates.ContractMergeDecision. Any failure leaves every
    customer, contract and presentation value exactly as it was before the call.
    """
    require_manager(user)
    duplicate_ids = list(dict.fromkeys(str(value) for value in duplicate_ids))
    if not duplicate_ids:
        raise ValidationError('통합할 중복 고객사를 한 곳 이상 선택해 주세요.')
    if str(primary_id) in duplicate_ids:
        raise ValidationError('유지할 고객사는 중복 고객사 목록에서 제외해 주세요.')
    with transaction.atomic():
        primary = Customer.objects.select_for_update().select_related('organization').get(pk=primary_id)
        if primary.merged_into_id:
            raise ValidationError('유지할 고객사가 이미 다른 고객사로 통합되었습니다. 새로고침한 뒤 다시 선택해 주세요.')
        duplicates = list(Customer.objects.select_for_update().select_related('organization').filter(pk__in=duplicate_ids))
        if len(duplicates) != len(duplicate_ids):
            raise ValidationError('선택한 중복 고객사를 찾을 수 없습니다. 새로고침한 뒤 다시 선택해 주세요.')
        for duplicate in duplicates:
            if duplicate.merged_into_id:
                raise ValidationError(f'{duplicate}은(는) 이미 다른 고객사로 통합되었습니다. 새로고침한 뒤 다시 선택해 주세요.')
        duplicate_pks = {duplicate.pk for duplicate in duplicates}

        # Resolve the conflicting name/category/region/visibility values onto the kept customer first,
        # reusing the same tested presentation logic as a normal edit.
        primary = save_presentation(user, presentation_data, customer_id=primary.pk, extra_name_exclusions=duplicate_pks)

        primary_contracts = {str(c.pk): c for c in Contract.objects.select_for_update().filter(customer_id=primary.pk)}
        moving_contracts = {str(c.pk): c for c in Contract.objects.select_for_update().filter(customer_id__in=duplicate_pks)}
        # Already-ended contracts move over as history without a planner decision; only
        # currently active ones can double count, so only those need an explicit choice.
        active_moving = {contract_id: c for contract_id, c in moving_contracts.items() if c.is_active}
        valid_targets = set(primary_contracts) | set(moving_contracts)
        try:
            resolve_contract_merge(active_moving.keys(), contract_decisions, valid_targets)
        except ValueError as error:
            raise ValidationError(str(error)) from error

        for contract in moving_contracts.values():
            contract.customer = primary
        for contract_id, decision in contract_decisions.items():
            contract = active_moving[contract_id]
            if decision.action == 'exclude':
                contract.is_active = False
                contract.superseded_by = primary_contracts.get(decision.superseded_by) or moving_contracts[decision.superseded_by]
            else:
                contract.superseded_by = None
        for contract in moving_contracts.values():
            contract.full_clean()
            contract.save()

        for duplicate in duplicates:
            duplicate.merged_into = primary
            duplicate.merged_at = timezone.now()
            duplicate.show_in_list = False
            duplicate.include_in_total = False
            duplicate.full_clean()
            duplicate.save()
        return primary

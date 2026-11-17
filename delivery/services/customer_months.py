"""고객사 관리의 월별 보기(2026-11-17 형우: "추가된 고객사를 월별로 볼 수 있으면 이번 달에 신규 추가된 고객사를 보고 관리할 수
있을 것 같은데" / "등록월, 계약월 기준을 둘 다 볼 수 있으면 좋을 것 같은데").

기준 두 가지:
- 등록월(registered): 고객사 관리에 넣은 달. 신규 고객사 = 그 달에 고객사를 등록. 계약 추가 = 그 전에 등록한 고객사에 그 달 새 계약을 등록.
- 계약월(contract): 계약서의 계약일. 신규 고객사 = 첫 계약일이 그 달. 계약 추가 = 이전 계약이 있는 고객사가 그 달에 또 계약.
  계약일이 비어 있는 계약은 어느 달에도 안 잡히므로 '계약일 미입력'으로 따로 모은다(다른 부서 자료가 오면 채울 목록).
처음 옮겨 온 자료(BASELINE_UNTIL까지 입력)는 등록월 기준에서 달로 나누지 않고 '기존 자료' 하나로 묶는다 — 신규와 섞이지 않게.
중복 통합으로 제외된 계약(superseded)은 세지 않는다. 통합된 고객사(merged_into)는 목록에 없다.
"""
from collections import defaultdict
from datetime import date
from django.utils import timezone
from delivery.models import Contract, Customer

BASELINE_UNTIL = date(2026, 10, 22)   # 인터넷 서버로 옮긴 날(2026-10-22)까지가 처음 입력한 기존 자료


def _month(day):
    return f'{day.year:04d}-{day.month:02d}'


def _local_day(moment):
    return timezone.localtime(moment).date()


def month_label(key):
    if key == 'base':
        return f'기존 자료({BASELINE_UNTIL:%Y.%m.%d}까지 처음 입력)'
    if key == 'nodate':
        return '계약일 미입력'
    year, month = key.split('-')
    return f'{year}년 {int(month)}월'


def month_index(basis):
    """{고객사 id: {월 키: ('new' | 'added', 그 달의 대표 날짜)}} 와 월 목록 [(키, 이름, 신규 수, 추가 수)]."""
    customers = {row['id']: _local_day(row['created_at'])
                 for row in Customer.objects.filter(merged_into__isnull=True).values('id', 'created_at')}
    contracts = Contract.objects.filter(customer_id__in=customers, superseded_by__isnull=True).values(
        'customer_id', 'created_at', 'contract_date')
    marks = defaultdict(dict)
    if basis == 'contract':
        dated = defaultdict(list)
        for row in contracts:
            if row['contract_date']:
                dated[row['customer_id']].append(row['contract_date'])
            else:
                marks[row['customer_id']].setdefault('nodate', ('new', None))
        for customer_id, days in dated.items():
            first = min(days)
            for day in sorted(days, reverse=True):
                key = _month(day)
                kind = 'new' if _month(first) == key else 'added'
                if key not in marks[customer_id] or kind == 'new':
                    marks[customer_id][key] = (kind, day)
    else:
        for customer_id, created in customers.items():
            marks[customer_id]['base' if created <= BASELINE_UNTIL else _month(created)] = ('new', created)
        for row in contracts:
            created = _local_day(row['created_at'])
            customer_created = customers[row['customer_id']]
            if created <= BASELINE_UNTIL:
                continue
            key = _month(created)
            if _month(customer_created) == key and customer_created > BASELINE_UNTIL:
                continue                      # 그 달에 새로 등록한 고객사의 첫 계약은 '신규'에 이미 들어 있다
            current = marks[row['customer_id']].get(key)
            if current is None or (current[0] == 'added' and current[1] < created):
                marks[row['customer_id']][key] = ('added', created)
    counts = defaultdict(lambda: [0, 0])
    for customer_marks in marks.values():
        for key, (kind, _day) in customer_marks.items():
            counts[key][0 if kind == 'new' else 1] += 1
    order = sorted((key for key in counts if key not in {'base', 'nodate'}), reverse=True)
    order += [key for key in ('nodate', 'base') if key in counts]
    months = [(key, month_label(key), counts[key][0], counts[key][1]) for key in order]
    return marks, months


def note_for(basis, kind, day):
    if day is None:
        return '계약일 미입력'
    word = '신규' if kind == 'new' else '계약 추가'
    return f'{word} · {day:%Y.%m.%d} {"등록" if basis == "registered" else "계약"}'

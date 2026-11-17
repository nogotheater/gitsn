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
    """{고객사 id: {월 키: ('new' | 'added', 그 달의 대표 날짜)}}, 월별 숫자 {월 키: {'new': 신규 고객사 수,
    'added': 계약 추가 고객사 수, 'contracts': 기존 고객사의 추가 계약 건수}}.

    '계약 N건'(2026-11-17 형우 (나)): 신규 고객사의 계약은 빼고, 기존 고객사가 그 달에 추가한 계약 건수.
    """
    customers = {row['id']: _local_day(row['created_at'])
                 for row in Customer.objects.filter(merged_into__isnull=True).values('id', 'created_at')}
    contracts = list(Contract.objects.filter(customer_id__in=customers, superseded_by__isnull=True).values(
        'customer_id', 'created_at', 'contract_date'))
    marks = defaultdict(dict)
    added_contracts = defaultdict(int)
    if basis == 'contract':
        dated = defaultdict(list)
        for row in contracts:
            if row['contract_date']:
                dated[row['customer_id']].append(row['contract_date'])
            else:
                marks[row['customer_id']].setdefault('nodate', ('new', None))
        for customer_id, days in dated.items():
            first = _month(min(days))
            for day in sorted(days, reverse=True):
                key = _month(day)
                if key == first:
                    marks[customer_id][key] = ('new', min(d for d in days if _month(d) == key))
                else:
                    added_contracts[key] += 1
                    if key not in marks[customer_id]:
                        marks[customer_id][key] = ('added', day)
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
                continue                      # 그 달에 새로 등록한 고객사의 계약은 '신규'에 들어 있다
            added_contracts[key] += 1
            current = marks[row['customer_id']].get(key)
            if current is None or (current[0] == 'added' and current[1] < created):
                marks[row['customer_id']][key] = ('added', created)
    stats = defaultdict(lambda: {'new': 0, 'added': 0, 'contracts': 0})
    for customer_marks in marks.values():
        for key, (kind, _day) in customer_marks.items():
            stats[key]['new' if kind == 'new' else 'added'] += 1
    for key, count in added_contracts.items():
        stats[key]['contracts'] = count
    return marks, dict(stats)


def years_of(stats, basis, today):
    years = sorted({int(key[:4]) for key in stats if key[:1].isdigit()} | ({today.year} if basis == 'registered' else set()), reverse=True)
    return years or [today.year]


def chart(stats, basis, year, selected, today, link):
    """그 해 열두 달(등록월은 처음 입력한 자료 다음 달부터) 막대. 높이 = 신규 곳 + 추가 계약 건, 가장 큰 달이 150px."""
    first = BASELINE_UNTIL.month if basis == 'registered' and year == BASELINE_UNTIL.year else 1
    if basis == 'registered' and year < BASELINE_UNTIL.year:
        return [], 0
    months = []
    for month in range(first, 13):
        key = f'{year:04d}-{month:02d}'
        row = stats.get(key, {'new': 0, 'added': 0, 'contracts': 0})
        future = (year, month) > (today.year, today.month)
        months.append({'key': key, 'month': month, 'new': row['new'], 'contracts': row['contracts'],
                       'future': future, 'current': (year, month) == (today.year, today.month),
                       'selected': key == selected, 'url': link(key)})
    peak = max([m['new'] + m['contracts'] for m in months] + [1])
    for m in months:
        total = m['new'] + m['contracts']
        m['height'] = round(150 * total / peak) if total else 0
        m['h_new'] = round(m['height'] * m['new'] / total) if total else 0
        m['h_added'] = m['height'] - m['h_new']
    return months, first


def note_for(basis, kind, day):
    if day is None:
        return '계약일 미입력'
    word = '신규' if kind == 'new' else '계약 추가'
    return f'{word} · {day:%Y.%m.%d} {"등록" if basis == "registered" else "계약"}'

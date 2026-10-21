"""지자체·의회 고객사의 소재지·기관 유형을 채운다(8단계 3단계).

  --report DIR            대조표(CSV, HTML)와 전국 대조 보고서를 만든다. DB는 바꾸지 않는다.
  --apply FILE.csv        형우 님이 확인한 대조표를 반영한다. '확인' 칸이 Y인 줄만 반영한다.
  --sept DIR              9월 대조 자료 폴더(sept_pdf_states.json, sept_tiles.json, sept_to_new.json)

실제 고객 데이터를 다루므로 개발 PC 안에서만 실행한다.
"""
import csv
import html
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from delivery.domain import admin_areas as aa
from delivery.domain.locations import ADMIN, FACILITY, format_location, guess_location, parse_location
from delivery.domain.region_map import CAMERA, EAVESDROP, FAMILY_LABEL, family_of_marker
from delivery.models import Category, Contract, Customer

TYPE_LABEL = {ADMIN: '행정기관', FACILITY: '시설·공기업', '': ''}
LABEL_TYPE = {'행정기관': ADMIN, '시설·공기업': FACILITY, '': ''}
ENTITY = {Category.LOCAL: 'municipality', Category.COUNCIL: 'council'}
ENTITY_LABEL = {'municipality': '지자체', 'council': '의회'}
PDF_FAMILY = {'audio': EAVESDROP, 'camera': CAMERA}
PDF_CUTOFF = date(2026, 8, 31)  # 9월 대조 PDF는 2026년 8월 기준(ver2608)
COLUMNS = ['고객사ID', '분류', '권역', '기관명', '현재_소재지', '현재_기관유형', '추정_소재지', '추정_기관유형',
           '추정_근거', '9월_대조', '확정_소재지', '확정_기관유형', '확인', '메모']


def targets():
    return (Customer.objects.filter(category__in=[Category.LOCAL, Category.COUNCIL], merged_into__isnull=True)
            .select_related('organization').order_by('category', 'region', 'organization__official_name'))


def contract_families(customer_ids):
    """고객사별 {제품군: {'active': [계약일...], 'ended': bool}}"""
    out = defaultdict(lambda: defaultdict(lambda: {'active': [], 'ended': False}))
    rows = (Contract.objects.filter(customer_id__in=customer_ids)
            .values_list('customer_id', 'is_active', 'contract_date', 'product_lines__product__marker'))
    for cid, active, cdate, marker in rows:
        fam = family_of_marker(marker or '')
        if not fam:
            continue
        slot = out[cid][fam]
        if active:
            slot['active'].append(cdate)
        else:
            slot['ended'] = True
    return out


class Command(BaseCommand):
    help = '지자체·의회 고객사 소재지·기관 유형 대조표 만들기(--report) / 확인본 반영(--apply)'

    def add_arguments(self, parser):
        parser.add_argument('--report', metavar='DIR')
        parser.add_argument('--apply', metavar='CSV')
        parser.add_argument('--sept', metavar='DIR')

    def handle(self, *args, **opts):
        if bool(opts['report']) == bool(opts['apply']):
            raise CommandError('--report 또는 --apply 중 하나만 지정하세요.')
        if opts['report']:
            self.report(Path(opts['report']), Path(opts['sept']) if opts['sept'] else None)
        else:
            self.apply(Path(opts['apply']))

    # ---------- 대조표 ----------
    def report(self, outdir, septdir):
        outdir.mkdir(parents=True, exist_ok=True)
        customers = list(targets())
        fams = contract_families([c.pk for c in customers])
        sept = self.load_sept(septdir) if septdir else None
        rows, unit_system = [], defaultdict(lambda: defaultdict(list))
        for c in customers:
            name = str(c)
            g = guess_location(name, c.category, c.region)
            loc = c.location_code or g.location_code
            ent = ENTITY[c.category]
            sept_note = ''
            if sept and loc in aa.UNIT_BY_CODE:
                notes = []
                for fam, slot in fams[c.pk].items():
                    if not slot['active']:
                        continue
                    unit_system[(fam, ent)][loc].append((name, min((d for d in slot['active'] if d), default=None)))
                    states = sept.get((fam, ent))
                    if states is None:
                        notes.append(f'{FAMILY_LABEL[fam]}: 9월 자료 없음')
                    else:
                        notes.append(f'{FAMILY_LABEL[fam]}: ' + ('9월 도입 표시와 일치' if loc in states else '9월에는 미도입'))
                sept_note = ' / '.join(notes)
            rows.append({
                '고객사ID': str(c.pk), '분류': c.get_category_display(), '권역': c.get_region_display(), '기관명': name,
                '현재_소재지': format_location(c.location_code), '현재_기관유형': TYPE_LABEL[c.institution_type],
                '추정_소재지': format_location(g.location_code), '추정_기관유형': TYPE_LABEL[g.institution_type],
                '추정_근거': g.reason, '9월_대조': sept_note,
                '확정_소재지': format_location(loc), '확정_기관유형': TYPE_LABEL[c.institution_type or g.institution_type],
                '확인': '', '메모': '',
            })
        diffs = self.national_diff(sept, unit_system, customers, fams) if sept else []
        with open(outdir / '03_location_review.csv', 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        (outdir / '03_location_review.html').write_text(self.render_html(rows, diffs), encoding='utf-8')
        blank = sum(1 for r in rows if not r['확정_소재지'])
        stop = sum(1 for d in diffs if d['분류'] == '확인 필요')
        self.stdout.write(f'고객사 {len(rows)}곳, 소재지 비어 있음 {blank}곳, 전국 대조 차이 {len(diffs)}건(확인 필요 {stop}건)')

    def load_sept(self, d):
        states = json.loads((d / 'sept_pdf_states.json').read_text(encoding='utf-8'))
        tiles = {str(t['id']): t for t in json.loads((d / 'sept_tiles.json').read_text(encoding='utf-8'))['tiles']}
        to_new = {str(r['tile_id']): r['new_codes'] for r in json.loads((d / 'sept_to_new.json').read_text(encoding='utf-8'))}
        out = {}
        for key, ds in states.items():
            fam_key, ent = key.split(':')
            units = set()
            for tid, on in ds['states'].items():
                if on and not tiles[tid].get('macro') and tid in to_new:
                    units.update(to_new[tid])
            out[(PDF_FAMILY[fam_key], ent)] = units
        return out

    def national_diff(self, sept, unit_system, customers, fams):
        by_unit = defaultdict(list)
        for c in customers:
            loc = c.location_code or guess_location(str(c), c.category, c.region).location_code
            by_unit[(ENTITY[c.category], loc)].append(c)
        incheon_pairs = [set(v) for v in aa.INCHEON_REORG.values() if len(v) > 1]
        out = []
        for (fam, ent), pdf_units in sorted(sept.items()):
            sys_units = unit_system[(fam, ent)]
            for u in sorted(pdf_units - set(sys_units)):
                if any(u in pair and pair & set(sys_units) for pair in incheon_pairs):
                    continue  # 인천 개편: 예전 한 칸이 두 구로 나뉨. 둘 중 하나가 도입이면 같은 기관으로 본다
                here = by_unit.get((ent, u), [])
                if any(fams[c.pk][fam]['ended'] and not fams[c.pk][fam]['active'] for c in here):
                    kind = '계약 종료'
                else:
                    kind = '확인 필요'
                out.append({'제품군': FAMILY_LABEL[fam], '대상': ENTITY_LABEL[ent], '면': format_location(u),
                            '방향': '9월 PDF에만 도입', '분류': kind,
                            '시스템 기관': ', '.join(str(c) for c in here) or '(이 면에 기관 없음)'})
            for u, items in sorted(sys_units.items()):
                if u in pdf_units:
                    continue
                if any(u in pair and pair & pdf_units for pair in incheon_pairs):
                    continue
                first = min((d for _n, d in items if d), default=None)
                kind = '9월 이후 신규' if first and first > PDF_CUTOFF else '확인 필요'
                out.append({'제품군': FAMILY_LABEL[fam], '대상': ENTITY_LABEL[ent], '면': format_location(u),
                            '방향': '시스템에만 도입', '분류': kind,
                            '시스템 기관': ', '.join(f'{n}({d or "계약일 없음"})' for n, d in items)})
        return out

    def render_html(self, rows, diffs):
        e = html.escape
        def table(items, cols):
            head = ''.join(f'<th>{e(c)}</th>' for c in cols)
            body = ''.join('<tr>' + ''.join(f'<td>{e(str(r.get(c, "")))}</td>' for c in cols) + '</tr>' for r in items)
            return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
        need = [r for r in rows if not r['확정_소재지'] or '선택 필요' in r['추정_근거'] or '후보' in r['추정_근거']]
        differ = [r for r in rows if '9월에는 미도입' in r['9월_대조']]
        cols = ['기관명', '분류', '권역', '확정_소재지', '확정_기관유형', '추정_근거', '9월_대조']
        stop = [d for d in diffs if d['분류'] == '확인 필요']
        return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>3단계 소재지 대조표</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#1b2430}}table{{border-collapse:collapse;margin:8px 0 24px;width:100%}}
td,th{{border:1px solid #d9dee5;padding:4px 8px;text-align:left;vertical-align:top}}th{{background:#f3f5f8}}h2{{margin-top:32px}}.n{{color:#5a6472}}</style></head><body>
<h1>3단계 소재지·기관 유형 대조표</h1>
<p class="n">고객사 {len(rows)}곳(지자체·의회, 통합된 중복 제외). DB는 아직 바꾸지 않았습니다. 수정은 같은 폴더의 <b>03_location_review.csv</b>에서 합니다.</p>
<ol><li>아래 1·2번 목록을 보고, CSV의 <b>확정_소재지</b>(예: "충남 천안시", "서울", "인천 영종구")와 <b>확정_기관유형</b>(행정기관 / 시설·공기업)을 고칩니다.</li>
<li>모든 줄의 <b>확인</b> 칸에 Y를 적고 저장합니다(엑셀에서 Y를 아래로 끌어 채우면 됩니다).</li>
<li>Claude에게 알려 주면 Y인 줄만 반영합니다.</li></ol>
<h2>1. 소재지를 정해야 하는 기관 ({len(need)}곳)</h2>{table(need, cols)}
<h2>2. 9월 PDF와 다른 기관 ({len(differ)}곳)</h2>{table(differ, cols)}
<h2>3. 전국 대조: 9월 PDF(8월 기준) ↔ 시스템 (차이 {len(diffs)}건, 확인 필요 {len(stop)}건)</h2>
<p class="n">면 단위로 비교했습니다. 9월 PDF는 시설도 면에 칠했으므로 여기서는 시설 포함 기준으로 비교합니다. "확인 필요"가 남으면 지도 작업을 멈추고 원인을 찾습니다.</p>
{table(diffs, ['제품군', '대상', '면', '방향', '분류', '시스템 기관'])}
<h2>4. 전체 목록 ({len(rows)}곳)</h2>{table(rows, cols)}
</body></html>'''

    # ---------- 반영 ----------
    def apply(self, path):
        with open(path, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        missing = [c for c in ('고객사ID', '확정_소재지', '확정_기관유형', '확인') if c not in (rows[0] if rows else {})]
        if missing:
            raise CommandError(f'대조표 칸이 없습니다: {missing}')
        plan, errors, skipped = [], [], []
        for i, r in enumerate(rows, 2):
            if r['확인'].strip().upper() != 'Y':
                skipped.append(r['기관명'])
                continue
            try:
                code = parse_location(r['확정_소재지'])
                kind = LABEL_TYPE[r['확정_기관유형'].strip()]
            except (ValueError, KeyError) as exc:
                errors.append(f'{i}행 {r["기관명"]}: {exc}')
                continue
            plan.append((r['고객사ID'], code, kind))
        if errors:
            raise CommandError('반영하지 않았습니다. 고칠 곳:\n' + '\n'.join(errors))
        changed = 0
        with transaction.atomic():
            for cid, code, kind in plan:
                c = Customer.objects.select_for_update().get(pk=cid)
                if (c.location_code, c.institution_type) != (code, kind):
                    c.location_code, c.institution_type = code, kind
                    c.save(update_fields=['location_code', 'institution_type', 'updated_at'])
                    changed += 1
        # 반영 결과를 확인본과 다시 대조
        mismatch = [cid for cid, code, kind in plan
                    if tuple(Customer.objects.filter(pk=cid).values_list('location_code', 'institution_type')[0]) != (code, kind)]
        self.stdout.write(f'확인된 줄 {len(plan)}개, 바뀐 고객사 {changed}곳, 건너뛴 줄(확인 없음) {len(skipped)}개, 불일치 {len(mismatch)}개')
        if skipped:
            self.stdout.write('건너뜀: ' + ', '.join(skipped))
        if mismatch:
            raise CommandError(f'반영 후 불일치: {mismatch}')

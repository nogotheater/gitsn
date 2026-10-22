"""중앙정부 나열 순서(2026-10-22 형우 확정).

청와대 → 국회 → 헌법기관 → 대통령 소속·독립기관 → 국무총리 소속 → 행정각부(정부조직법 제29조 순서, 2026-10-02 시행).
각 부 바로 뒤에 그 부 소속 청·기관. 앞으로 등록하는 기관도 이 기준으로 놓는다:
- 아래 목록에 있는 이름은 목록 자리에.
- 목록에 없는 이름은 이름에 든 말(예: '경찰', '국방', '해양경찰')로 소속 묶음을 찾아 그 묶음 끝에(가나다순).
- 어디에도 맞지 않으면 중앙정부 맨 끝에(가나다순).
DB를 쓰지 않는다.
"""

# (묶음, [이 묶음 안의 순서대로 이름]) — 묶음 순서가 곧 나열 순서다.
BLOCKS = (
    ('head', ['청와대', '대통령실', '대통령비서실', '대한민국 국회', '국회', '대법원', '헌법재판소', '중앙선거관리위원회']),
    ('president', ['감사원', '국가정보원', '대통령경호처', '국가안보실', '고위공직자범죄수사처']),
    ('pm', ['국무총리실', '국무조정실', '국무총리비서실', '기획예산처', '인사혁신처', '법제처', '식품의약품안전처',
            '국가데이터처', '지식재산처', '금융위원회', '공정거래위원회', '국민권익위원회', '개인정보보호위원회', '원자력안전위원회']),
    ('moef', ['재정경제부', '국세청', '관세청', '조달청']),
    ('msit', ['과학기술정보통신부', '우주항공청', '우정사업본부']),
    ('moe', ['교육부', '교원소청심사위원회', '국립특수교육원', '중앙교육연수원']),
    ('mofa', ['외교부', '재외동포청']),
    ('unikorea', ['통일부']),
    ('moj', ['법무부', '공소청']),
    ('mnd', ['국방부', '병무청', '방위사업청', '합동참모본부', '육군', '해군', '해병대', '공군', '전략사령부', '드론작전사령부',
             '국방부조사본부', '한미연합군사령부']),
    ('mois', ['행정안전부', '행정안전부 정부청사관리본부', '서울청사관리소', '대전청사관리소', '국가정보자원관리원', '대통령기록관',
              '경찰청', '경찰인재개발원', '경찰수사연수원', '소방청', '중대범죄수사청']),
    ('mpva', ['국가보훈부']),
    ('mcst', ['문화체육관광부', '국립중앙도서관', '국립중앙박물관', '국가유산청', '조선왕릉동부지구관리소', '창경궁 관리소']),
    ('mafra', ['농림축산식품부', '국립농산물품질관리원', '농림축산검역본부', '국립종자원', '농식품공무원교육원', '농촌진흥청',
               '국립농업과학원', '국립원예특작과학원', '산림청']),
    ('motie', ['산업통상부']),
    ('mohw', ['보건복지부', '질병관리청']),
    ('me', ['기후에너지환경부', '기상청']),
    ('moel', ['고용노동부']),
    ('mogef', ['성평등가족부']),
    ('molit', ['국토교통부', '행정중심복합도시건설청', '새만금개발청']),
    ('mof', ['해양수산부', '해양경찰청', '해양경찰정비창']),
    ('mss', ['중소벤처기업부']),
)

# 목록에 없는 이름: 앞에서부터 처음 맞는 말로 묶음을 정한다(더 좁은 말을 먼저).
KEYWORDS = (
    ('해양경찰', 'mof'), ('경찰', 'mois'), ('소방', 'mois'), ('중대범죄', 'mois'),
    ('청와대', 'head'), ('대통령실', 'head'), ('국회', 'head'), ('헌법재판', 'head'), ('선거관리', 'head'), ('법원', 'head'),
    ('감사원', 'president'), ('국가정보원', 'president'), ('경호', 'president'), ('고위공직자', 'president'), ('공수처', 'president'),
    ('대통령기록', 'mois'), ('국가기록', 'mois'), ('정부청사', 'mois'), ('청사관리', 'mois'), ('행정안전', 'mois'),
    ('국방', 'mnd'), ('합동참모', 'mnd'), ('육군', 'mnd'), ('해군', 'mnd'), ('해병', 'mnd'), ('공군', 'mnd'), ('사령부', 'mnd'),
    ('국군', 'mnd'), ('병무', 'mnd'), ('방위사업', 'mnd'),
    ('재정경제', 'moef'), ('국세', 'moef'), ('세관', 'moef'), ('관세', 'moef'), ('조달', 'moef'),
    ('과학기술', 'msit'), ('우정', 'msit'), ('우주항공', 'msit'), ('전파', 'msit'),
    ('교육', 'moe'), ('교원', 'moe'),
    ('외교', 'mofa'), ('재외동포', 'mofa'), ('통일', 'unikorea'),
    ('법무', 'moj'), ('공소', 'moj'), ('검찰', 'moj'), ('교정', 'moj'), ('출입국', 'moj'),
    ('보훈', 'mpva'),
    ('국가유산', 'mcst'), ('왕릉', 'mcst'), ('궁', 'mcst'), ('문화', 'mcst'), ('박물관', 'mcst'), ('도서관', 'mcst'), ('체육', 'mcst'), ('관광', 'mcst'),
    ('농림', 'mafra'), ('농식품', 'mafra'), ('농산물', 'mafra'), ('농업', 'mafra'), ('농촌', 'mafra'), ('원예', 'mafra'),
    ('종자', 'mafra'), ('검역', 'mafra'), ('산림', 'mafra'),
    ('산업통상', 'motie'),
    ('보건', 'mohw'), ('복지', 'mohw'), ('질병', 'mohw'),
    ('기후', 'me'), ('환경', 'me'), ('기상', 'me'),
    ('고용', 'moel'), ('노동', 'moel'),
    ('성평등', 'mogef'), ('가족', 'mogef'),
    ('국토', 'molit'), ('행정중심복합', 'molit'), ('새만금', 'molit'),
    ('해양', 'mof'), ('수산', 'mof'), ('항만', 'mof'),
    ('중소', 'mss'), ('벤처', 'mss'),
    ('총리', 'pm'), ('국무조정', 'pm'), ('인사혁신', 'pm'), ('법제처', 'pm'), ('식품의약', 'pm'), ('데이터처', 'pm'),
    ('지식재산', 'pm'), ('위원회', 'pm'),
)

_BLOCK_INDEX = {key: index for index, (key, _names) in enumerate(BLOCKS)}
_KNOWN = {}
for _block_index, (_key, _names) in enumerate(BLOCKS):
    for _position, _name in enumerate(_names):
        _KNOWN.setdefault(' '.join(_name.split()), (_block_index, _position))


def _normal(name):
    return ' '.join((name or '').split())


def central_block(name):
    """이름 → 묶음 키(목록 또는 이름에 든 말로). 맞는 곳이 없으면 None."""
    normal = _normal(name)
    if normal in _KNOWN:
        return BLOCKS[_KNOWN[normal][0]][0]
    for word, key in KEYWORDS:
        if word in normal:
            return key
    return None


def central_sort_key(name):
    """중앙정부 정렬 키: (묶음 순서, 묶음 안 자리, 이름). 목록 밖 이름은 묶음 끝, 묶음도 없으면 맨 끝."""
    normal = _normal(name)
    if normal in _KNOWN:
        block, position = _KNOWN[normal]
        return (block, position, normal.casefold())
    key = central_block(normal)
    block = _BLOCK_INDEX[key] if key else len(BLOCKS)
    return (block, 10_000, normal.casefold())


def name_order_key(category, name):
    """섹션 안 이름 순서: 중앙정부는 위 기준, 민간은 재계순위(private_order), 나머지 분류는 가나다순. 화면·인쇄가 같은 키를 쓴다."""
    if category == 'central':
        return central_sort_key(name)
    if category == 'private':
        from .private_order import private_sort_key
        return private_sort_key(name)
    return (0, 0, _normal(name).casefold())

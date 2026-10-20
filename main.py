"""상속 길잡이 카카오 스킬 서버 v2 (문서 기준 정렬판)

실행:   uv run uvicorn main:app --port 8000
필요:   uv add httpx
확인:   GET /  ->  {"status": "ok"}
카카오 스킬 URL:  https://<Render 주소>/skill

문서 기준
- 화면정의서 v1.4: K-01(관계·사망일·안심상속) -> K-02(기본 체크리스트) -> K-03(위험 질문 3개) -> 웹 링크
- 결정 문서 Q21(관계 선택지), Q76~Q82(위험 질문), 개인정보 최종정책(로그 금지, 서버 메모리 일시 보관)

환경변수 (모두 비어 있어도 서버는 동작하고, 백엔드 호출만 건너뜁니다)
  STARTER_KIT_API_URL    백엔드 주소. 예: https://starter-kit.onrender.com
  HANDOFF_SERVER_SECRET  서버끼리 쓰는 비밀값 (백엔드와 같은 값)
  FRONTEND_ORIGIN        웹 주소. 예: https://starter-kit-web.onrender.com
  HANDOFF_PATH           인계 토큰 발급 경로 (기본 /api/handoff, 협의 후 확정)
  RECOMMEND_PATH         추천 API 경로 (기본 /api/checklist/recommend, 협의 후 확정)
  HANDOFF_QUERY_KEY      웹 링크의 토큰 이름 (기본 handoff, 이정민 님과 협의)
  DEATH_INPUT_MODE       date(기본, 날짜 입력) 또는 period(기간 버튼)
"""
import os
import re
import time
import datetime

import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="상속 길잡이 스킬 서버")

STARTER_KIT_API_URL = os.getenv("STARTER_KIT_API_URL", "").rstrip("/")
HANDOFF_SERVER_SECRET = os.getenv("HANDOFF_SERVER_SECRET", "")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").rstrip("/")
HANDOFF_PATH = os.getenv("HANDOFF_PATH", "/api/handoff")
RECOMMEND_PATH = os.getenv("RECOMMEND_PATH", "/api/checklist/recommend")
HANDOFF_QUERY_KEY = os.getenv("HANDOFF_QUERY_KEY", "handoff")
DEATH_INPUT_MODE = os.getenv("DEATH_INPUT_MODE", "date")

SESSION_TTL = 1800      # 대화 중 답변을 서버 메모리에 보관하는 시간(초). 제안값, 정책 V01 확인 후 확정
API_TIMEOUT = 3.0       # 카카오 응답 제한 5초 안에 끝내기 위한 백엔드 호출 제한(초)

COMMON_WARNING = "주의: 기한·채무는 공식 자료로 확인하세요."
LEGAL_NOTE = "법적 영향은 대한법률구조공단에 상담하세요."
FALLBACK_TEXT = "아직 이해하지 못했어요. 아래 메뉴에서 골라 주세요.\n\n" + COMMON_WARNING
ERROR_TEXT = "안내를 불러오지 못했습니다.\n\n" + COMMON_WARNING

# ---------------------------------------------------------------
# 1) 질문 선택지 (결정 문서 Q21, Q76, 화면정의서 K-01)
# ---------------------------------------------------------------
RELATIONS = [  # [버튼 문구, 백엔드로 보낼 값(제안)]
    ["배우자", "spouse"],
    ["자녀·손자녀", "child_grandchild"],
    ["부모·조부모", "parent_grandparent"],
    ["형제자매", "sibling"],
    ["기타 친족", "other_relative"],
    ["그 외·모름", "other_unknown"],
]
ONESTOP = [["신청함", "applied"], ["미신청", "not_applied"], ["모름", "unknown"]]
PERIODS = [["1개월 이내", "within_1m"], ["1~3개월", "1_to_3m"], ["3개월 이상", "over_3m"]]
YESNO = [["있음", "yes"], ["없음", "no"], ["모름", "unknown"]]
RISKS = [  # [키, 버튼 문구, 질문 문장]
    ["debtGuarantee", "채무·보증", "고인에게 채무나 보증이 있나요?"],
    ["assetDisposal", "재산 처분·사용", "사망 후 고인의 재산이 처분되거나 사용된 사실을 알고 있나요?\n(본인이 아닌 다른 사람의 행동도 포함합니다)"],
    ["ownApplication", "본인 신청", "본인이 상속포기 또는 한정승인을 신청했나요?\n(다른 상속인의 신청은 포함하지 않습니다)"],
]

# ---------------------------------------------------------------
# 2) 안내 블록: 기존 시연용 문구. 검수된 문구로 교체 전까지 "시연용" 표시 유지
#    qr = [버튼 문구, 이동할 블록 키]
# ---------------------------------------------------------------
NODES = {
    "finance": {
        "name": "금융·채무",
        "text": "주의: 기한·채무는 공식 자료로 확인하세요.\n\n안심상속 원스톱 서비스로 금융기관 예금·대출·보험, 국세·지방세, 자동차, 토지 정보를 한 번에 조회할 수 있습니다. 시·군·구청이나 주민센터, 정부24에서 신청합니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "상속세",
                "tax"
            ],
            [
                "위험 행동 확인",
                "risk"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "tax": {
        "name": "상속세",
        "text": "상속세는 사망일이 속한 달의 말일부터 6개월 이내에 신고·납부하는 것이 기본입니다. 상속재산 규모에 따라 신고 대상 여부가 달라지니 국세청에서 확인하세요.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "법령·시행일 확인",
                "law"
            ],
            [
                "통신·구독",
                "telecom"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "telecom": {
        "name": "통신·구독",
        "text": "휴대전화·인터넷 명의 변경이나 해지, OTT·클라우드·쇼핑몰 정기결제 해지, 간편결제·포인트 정리를 확인하세요. 해지 전에 사진·문서 백업이 필요한지 가족과 상의하세요.",
        "qr": [
            [
                "금융·채무",
                "finance"
            ],
            [
                "위험 행동 확인",
                "risk"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "law": {
        "name": "법령·시행일 확인",
        "text": "상속 관련 법령은 개정될 수 있고, 이 시연 화면은 최신 법령을 조회하지 않습니다. 국가법령정보센터(law.go.kr)에서 현행 법령과 시행일을 확인하세요.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "상속세",
                "tax"
            ],
            [
                "위험 행동 확인",
                "risk"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp": {
        "name": "특수 상황 목록",
        "text": "일반 순위로 설명하기 어려운 상황을 골라 주세요. 해당하는 항목이 없으면 '기간 확인'을 눌러 이어가세요.",
        "qr": [
            [
                "태아·대습상속",
                "sp_unborn"
            ],
            [
                "사실혼·이혼",
                "sp_partner"
            ],
            [
                "혼외자·양자",
                "sp_child"
            ],
            [
                "외국인·북한",
                "sp_foreign"
            ],
            [
                "상속결격·상실",
                "sp_disq"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp_unborn": {
        "name": "특수_태아·대습상속",
        "text": "태아: 상속이 시작될 때 태어나지 않았어도 이미 태어난 것으로 보아 상속인이 됩니다(민법 제1000조 제3항). 단, 살아서 태어나야 합니다.\n\n대습상속: 상속인이 될 자녀나 형제자매가 상속 개시 전에 사망했거나 결격·상속권 상실로 상속인이 되지 못하면, 그 사람의 직계비속과 배우자가 대신 상속인이 됩니다(제1001조). 예) 할아버지가 돌아가셨는데 아버지가 이미 돌아가셨다면 손자녀가 아버지 몫을 상속받습니다. 다만 결격으로 대습이 생긴 경우 그 사람의 배우자는 대습상속인이 될 수 없습니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "다른 특수 상황",
                "sp"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp_partner": {
        "name": "특수_사실혼·이혼",
        "text": "사실혼 배우자는 상속인이 아닙니다. 혼인신고를 한 법률상 배우자만 상속인입니다(제1003조). 다만 상속인이 없으면 특별연고자로서 법원에 상속재산 분여를 청구할 수 있고(상속인수색 공고기간 만료 후 2개월 이내), 사실혼을 입증하면 유족연금을 받을 수 있습니다.\n\n이혼소송 중이라도 이혼이 확정되기 전에 사망했다면 배우자는 상속인입니다. 이미 이혼한 배우자는 상속인이 아닙니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "다른 특수 상황",
                "sp"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp_child": {
        "name": "특수_혼외자·양자",
        "text": "혼외자: 아버지가 인지했거나 친생자관계가 확인되면 상속인입니다. 유언으로 인지한 경우도 포함됩니다.\n\n양자·친양자: 유효하게 입양했다면 직계비속으로 상속인이고, 양부모·친양부모도 상속인이 될 수 있습니다. 양자를 보낸 친생부모는 상속인이지만, 친양자를 보낸 친생부모는 상속인이 아닙니다. 유효하지 않은 입양은 상속인이 아닙니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "다른 특수 상황",
                "sp"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp_foreign": {
        "name": "특수_외국인·북한",
        "text": "외국 국적을 가진 상속인과 북한에 있는 상속인도 상속인이 될 수 있습니다.\n\n다만 고인(피상속인)이 외국인이면 상속인·순위·상속분이 고인의 본국법으로 정해집니다(국제사법 제77조 제1항). 외국에 재산이 있거나 외국에 사는 상속인이 있으면 재판 관할 문제가 생길 수 있어 전문가 상담을 권합니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "다른 특수 상황",
                "sp"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "sp_disq": {
        "name": "특수_상속결격·상실",
        "text": "상속결격: 고의로 피상속인이나 선순위·동순위 상속인을 살해했거나 살해하려 한 경우, 유언서를 위조·변조·파기·은닉한 경우 등(민법 제1004조)에는 상속인이 될 수 없습니다.\n\n상속권 상실: 부양의무를 중대하게 위반하는 등의 사유가 있으면 고인의 공정증서 유언 또는 공동상속인의 가정법원 청구(그 사람이 상속인이 되었음을 안 날부터 6개월 이내)로 상속권을 잃을 수 있습니다(제1004조의2). 부양을 소홀히 했다는 이유만으로 자동으로 결격이 되지는 않습니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "다른 특수 상황",
                "sp"
            ],
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "proc": {
        "name": "절차 핵심 안내",
        "text": "주의: 신청 가능 여부와 기한은 상황에 따라 다릅니다.\n\n상속포기·한정승인 핵심 절차\n1. 재산·채무 조사: 안심상속 원스톱 서비스로 금융·세금 정보를 확인합니다.\n2. 선택 판단: 그대로 받을지, 재산 범위 안에서만 빚을 갚을지(한정승인), 모두 포기할지 정합니다.\n3. 법원 신고: 상속이 시작된 것을 안 날부터 3개월 이내에 가정법원에 신고합니다.\n4. 기한이 지났다면 전문가 상담을 권합니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "금융·채무",
                "finance"
            ],
            [
                "위험 행동 확인",
                "risk"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "checklist": {
        "name": "기본 체크리스트",
        "text": "주의: 기한·채무는 공식 자료로 확인하세요.\n\n기본 체크리스트\n1. 상속인 확인 (가족관계증명서)\n2. 재산·채무 조사 (안심상속 원스톱 서비스)\n3. 상속포기·한정승인 판단 (3개월)\n4. 상속세 신고·납부 (6개월)\n5. 상속재산 명의 변경 (상속등기 등)\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "상속인 확인",
                "start"
            ],
            [
                "금융·채무",
                "finance"
            ],
            [
                "포기·한정승인 절차",
                "proc"
            ],
            [
                "상속세",
                "tax"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    }
}

NODES["welcome"] = {
    "name": "웰컴 블록",
    "text": "안녕하세요. 상속 길잡이입니다.\n\n가족의 사망 이후 필요한 절차를 확인하도록 도와드리겠습니다.\n\n어떤 내용이 궁금하신가요?",
    "qr": [["상속 절차 시작", "start"], ["기본 체크리스트", "checklist"], ["금융·채무", "finance"],
           ["상속세", "tax"], ["통신·구독", "telecom"], ["위험 행동 확인", "risk"], ["법령·시행일 확인", "law"]],
}
HOME = "welcome"


def norm(text: str) -> str:
    return re.sub(r"[\s·.,!?~\-_/()\[\]'\"]", "", text).lower()


LABELS = {norm(label): target for node in NODES.values() for label, target in node["qr"]}

KEYWORDS = [
    (re.compile(r"포기|한정승인|한정"), "proc"),
    (re.compile(r"체크리스트|할\s*일|순서"), "checklist"),
    (re.compile(r"태아|대습|손자|손녀"), "sp_unborn"),
    (re.compile(r"사실혼|이혼|동거"), "sp_partner"),
    (re.compile(r"혼외|입양|양자|인지"), "sp_child"),
    (re.compile(r"외국|북한|국적"), "sp_foreign"),
    (re.compile(r"결격|상속권\s*상실|불효"), "sp_disq"),
    (re.compile(r"특수|예외"), "sp"),
    (re.compile(r"법령|시행|개정|법률"), "law"),
    (re.compile(r"위험|처분|인출|주의"), "risk"),
    (re.compile(r"금융|채무|빚|대출|예금|안심상속"), "finance"),
    (re.compile(r"세금|상속세|증여"), "tax"),
    (re.compile(r"통신|구독|휴대|해지|결제"), "telecom"),
    (re.compile(r"시작|절차|상속\s*받|어떻게"), "start"),
    (re.compile(r"안녕|하이|헬로|hello|hi|ㅎㅇ|처음|메뉴|홈|도움|뭐|시작해", re.I), HOME),
]


def find_node(utterance: str):
    node_id = LABELS.get(norm(utterance))
    if node_id is None:
        for pattern, target in KEYWORDS:
            if pattern.search(utterance):
                return target
    return node_id


# ---------------------------------------------------------------
# 3) 대화 중 답변 보관 (서버 메모리에만, 일정 시간 뒤 삭제, 로그에 남기지 않음)
# ---------------------------------------------------------------
SESSIONS = {}


def get_session(uid: str) -> dict:
    now = time.time()
    for key in [k for k, v in SESSIONS.items() if now - v["ts"] > SESSION_TTL]:
        del SESSIONS[key]
    s = SESSIONS.get(uid)
    if s is None:
        s = {"step": None, "answers": {"riskAnswers": {}}, "ts": now}
        SESSIONS[uid] = s
    s["ts"] = now
    return s


def reset(s: dict):
    s["step"] = None
    s["answers"] = {"riskAnswers": {}}


# ---------------------------------------------------------------
# 4) 응답 만들기
# ---------------------------------------------------------------
def reply(text, labels, link=None):
    return {"text": text, "qr": labels, "link": link}


def node_reply(node_id):
    node = NODES[node_id]
    return reply(node["text"], [q[0] for q in node["qr"]])


def build(res: dict) -> dict:
    outputs = [{"simpleText": {"text": res["text"]}}]
    if res.get("link"):
        label, url = res["link"]
        outputs.append({"textCard": {
            "title": "웹 체크리스트",
            "description": "카카오톡에서 답한 내용을 웹에서 이어서 볼 수 있어요.",
            "buttons": [{"action": "webLink", "label": label, "webLinkUrl": url}],
        }})
    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": [{"label": l, "action": "message", "messageText": l} for l in res["qr"][:10]],
        },
    }


# ---------------------------------------------------------------
# 5) 질문 단계 (K-01 -> K-02 -> K-03)
# ---------------------------------------------------------------
def parse_date(text: str):
    """'2026-09-30', '2026.9.30', '20260930', '2026년 9월 30일' 형태를 날짜로 바꿉니다."""
    m = re.search(r"(\d{4})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})", text)
    if not m:
        return None
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    if d > datetime.date.today() or d.year < 1900:
        return None
    return d.isoformat()


def pick(options, text):
    key = norm(text)
    for label, value in options:
        if norm(label) == key:
            return value
    return None


def ask_relation():
    return reply("고인과 어떤 관계인가요?\n\n(1/3)", [r[0] for r in RELATIONS] + ["처음으로"])


def ask_death():
    if DEATH_INPUT_MODE == "period":
        return reply("고인이 돌아가신 지 얼마나 되었나요?\n\n(2/3)", [p[0] for p in PERIODS] + ["사망일 모름", "처음으로"])
    return reply("고인의 사망일을 알려 주세요.\n예) 2026-09-30\n\n모르면 '모름'을 눌러 주세요.\n\n(2/3)", ["모름", "처음으로"])


def ask_onestop():
    return reply("안심상속 원스톱 서비스를 신청하셨나요?\n\n(3/3)", [o[0] for o in ONESTOP] + ["처음으로"])


def risk_menu(s):
    done = s["answers"]["riskAnswers"]
    lines = ["추가 위험 확인은 선택입니다. 궁금한 질문만 골라서 답해도 되고, 답하지 않아도 체크리스트는 이용할 수 있어요.\n"]
    for key, label, _q in RISKS:
        lines.append(f"· {label}: {'답함' if key in done else '아직 안 함'}")
    lines.append("\n" + COMMON_WARNING)
    return reply("\n".join(lines), [r[1] for r in RISKS] + ["웹 체크리스트에서 보기", "처음으로"])


def risk_answer_text(key, value):
    if key == "assetDisposal":
        if value == "no":
            return "'없음'으로 기록했어요. 상속을 정하기 전에는 고인의 재산을 쓰거나 처분하지 않도록 주의하세요.\n\n" + LEGAL_NOTE
        # TODO: 검수된 응답별 문구(이정민 님 원고)로 교체. 답변만으로 법적 효과를 판단하지 않음(Q78, Q79)
        return ("재산이 처분되거나 사용된 사실은 상속을 어떻게 정할지에 영향을 줄 수 있어요. "
                "이 답변만으로 법적 결과를 판단하지는 않아요.\n\n" + COMMON_WARNING + "\n" + LEGAL_NOTE)
    # 채무·보증, 본인 신청은 응답별 문구가 아직 정해지지 않음(Q82 보류): 공통 위험 경고만 표시
    return COMMON_WARNING + "\n" + LEGAL_NOTE


async def call_backend(path, payload, secret=False):
    if not STARTER_KIT_API_URL:
        return None
    headers = {"X-Handoff-Secret": HANDOFF_SERVER_SECRET} if secret else {}
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            r = await client.post(STARTER_KIT_API_URL + path, json=payload, headers=headers)
        if r.status_code == 200:
            return r.json()
        print(f"[backend] {path} status={r.status_code}", flush=True)
    except Exception as e:
        print(f"[backend] {path} error={type(e).__name__}", flush=True)
    return None


async def show_result(s):
    a = s["answers"]
    data = await call_backend(RECOMMEND_PATH, a)
    labels = ["추가 위험 확인", "웹 체크리스트에서 보기", "기본 체크리스트", "처음으로"]
    recs = (data or {}).get("recommendations") if isinstance(data, dict) else None
    if recs:
        # TODO: 응답 필드 이름은 김현주 님과 확정 후 맞춤
        lines = [COMMON_WARNING, "", "먼저 확인하면 좋은 절차예요."]
        for i, r in enumerate(recs[:5], 1):
            title = r.get("title") or r.get("procedureName") or r.get("procedureId") or "절차"
            why = r.get("reason", "")
            lines.append(f"{i}. {title}" + (f" - {why}" if why else ""))
        return reply("\n".join(lines), labels)
    # 백엔드 추천이 아직 없을 때: 임시 기본 체크리스트
    return reply(NODES["checklist"]["text"], labels)


async def web_link(s):
    """K-02·K-03의 [웹 체크리스트에서 보기]: 누른 시점에 인계 토큰을 발급합니다(10분·1회)."""
    if not FRONTEND_ORIGIN:
        return reply("웹 주소가 아직 설정되지 않았습니다.\n\n" + COMMON_WARNING, ["처음으로"])
    data = await call_backend(HANDOFF_PATH, s["answers"], secret=True)
    token = (data or {}).get("token") if isinstance(data, dict) else None
    if token:
        url = f"{FRONTEND_ORIGIN}/?{HANDOFF_QUERY_KEY}={token}"
        return reply("아래 버튼을 누르면 웹에서 같은 답으로 이어서 볼 수 있어요. 링크는 10분 동안, 한 번만 열려요.",
                     ["처음으로"], link=("웹 체크리스트에서 보기", url))
    # D-15: 연결 실패 시 웹은 처음부터 시작
    return reply("답변을 웹으로 넘기지 못했어요. 웹에서는 처음부터 시작해 주세요.",
                 ["다시 시도", "처음으로"], link=("웹에서 시작하기", FRONTEND_ORIGIN))


def prompt_current(s):
    step = s["step"]
    if step == "relation":
        return ask_relation()
    if step == "death":
        return ask_death()
    if step == "onestop":
        return ask_onestop()
    if isinstance(step, str) and step.startswith("risk:"):
        key = step.split(":", 1)[1]
        q = next(r for r in RISKS if r[0] == key)
        return reply(q[2], [y[0] for y in YESNO] + ["다른 질문 확인"])
    return node_reply(HOME)


async def handle(s: dict, utterance: str, block_name: str):
    key = norm(utterance)

    # 처음으로 / 웰컴 블록 첫 진입
    if "웰컴" in block_name or key in ("처음으로", "처음", "메뉴", "홈"):
        reset(s)
        return node_reply(HOME), "welcome"
    if key == norm("다시 시도"):
        if s["step"] is None and s["answers"].get("relation"):
            return await web_link(s), "retry_link"
        return prompt_current(s), "retry"

    step = s["step"]

    # --- K-01 질문 3개 ---
    if step == "relation":
        value = pick(RELATIONS, utterance)
        if value:
            s["answers"]["relation"] = value
            s["step"] = "death"
            return ask_death(), "death"
        return ask_relation(), "relation_again"

    if step == "death":
        if key == "모름" or key == norm("사망일 모름"):
            s["answers"]["deathDate"] = None
            s["answers"]["deathDateUnknown"] = True
        elif DEATH_INPUT_MODE == "period" and pick(PERIODS, utterance):
            s["answers"]["deathDate"] = None
            s["answers"]["deathDateUnknown"] = False
            s["answers"]["deathPeriod"] = pick(PERIODS, utterance)
        else:
            d = parse_date(utterance) if DEATH_INPUT_MODE == "date" else None
            if not d:
                return reply("날짜를 읽지 못했어요. 2026-09-30처럼 입력하거나 '모름'을 눌러 주세요.", ["모름", "처음으로"]), "death_again"
            s["answers"]["deathDate"] = d
            s["answers"]["deathDateUnknown"] = False
        s["step"] = "onestop"
        return ask_onestop(), "onestop"

    if step == "onestop":
        value = pick(ONESTOP, utterance)
        if value:
            s["answers"]["oneStopStatus"] = value
            s["step"] = "result"
            return await show_result(s), "result"
        return ask_onestop(), "onestop_again"

    # --- K-03 위험 질문 (각각 골라서 답함, 순서 없음: Q81) ---
    if isinstance(step, str) and step.startswith("risk:"):
        rkey = step.split(":", 1)[1]
        value = pick(YESNO, utterance)
        if value:
            s["answers"]["riskAnswers"][rkey] = value
            s["step"] = "result"
            return reply(risk_answer_text(rkey, value), ["다른 질문 확인", "웹 체크리스트에서 보기", "처음으로"]), "risk_answered"
        if key == norm("다른 질문 확인"):
            s["step"] = "result"
            return risk_menu(s), "risk_menu"
        return prompt_current(s), "risk_again"

    # --- 단계 밖 버튼 ---
    if key in (norm("추가 위험 확인"), norm("다른 질문 확인")):
        s["step"] = "result" if s["answers"].get("relation") else None
        return risk_menu(s), "risk_menu"
    for rkey, label, _q in RISKS:
        if key == norm(label):
            s["step"] = f"risk:{rkey}"
            return prompt_current(s), "risk_question"
    if key == norm("웹 체크리스트에서 보기"):
        if not s["answers"].get("relation"):
            return reply("먼저 질문 3개에 답하면 웹으로 이어서 볼 수 있어요.", ["상속 절차 시작", "처음으로"]), "link_need_answers"
        return await web_link(s), "link"

    node_id = find_node(utterance)
    if node_id == "start":
        reset(s)
        s["step"] = "relation"
        return ask_relation(), "start"
    if node_id == "risk":
        return risk_menu(s), "risk_menu"
    if node_id is None:
        return reply(FALLBACK_TEXT, [q[0] for q in NODES[HOME]["qr"]]), "fallback"
    return node_reply(node_id), node_id


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/skill")
async def skill(request: Request):
    try:
        body = await request.json()
        user_request = body.get("userRequest") or {}
        utterance = (user_request.get("utterance") or "").strip()
        block_name = (user_request.get("block") or {}).get("name", "")
        uid = (user_request.get("user") or {}).get("id", "") or "anonymous"
        s = get_session(uid)
        res, tag = await handle(s, utterance, block_name)
        # 개인정보 정책: 사용자 입력 문장·식별값·답변 값은 로그에 남기지 않고 단계 이름만 남깁니다.
        print(f"[skill] step={s['step']} node={tag}", flush=True)
        return build(res)
    except Exception as e:  # 오류가 나도 안전한 안내를 돌려줍니다.
        print(f"[skill] ERROR {type(e).__name__}", flush=True)
        fallback = reply(ERROR_TEXT, ["다시 시도", "처음으로"],
                         link=("웹에서 시작하기", FRONTEND_ORIGIN) if FRONTEND_ORIGIN else None)
        return build(fallback)

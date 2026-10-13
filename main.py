"""상속 길잡이 카카오 스킬 서버 (시연용)

실행:  uv run uvicorn main:app --port 8000
확인:  http://localhost:8000/  ->  {"status": "ok"}
카카오 챗봇 관리자센터의 스킬 URL에는  https://<공개주소>/skill  을 등록합니다.
"""
import re

from fastapi import FastAPI, Request

app = FastAPI(title="상속 길잡이 스킬 서버")

# ---------------------------------------------------------------
# 대화 데이터: 웹 시연 페이지의 "블록 설계표"와 같은 내용입니다.
# 문구를 고치려면 이 부분의 text, qr(바로가기 응답)만 수정하세요.
# qr = [버튼 문구, 이동할 블록 키]
# ---------------------------------------------------------------
NODES = {
    "welcome": {
        "name": "웰컴 블록",
        "text": "안녕하세요. 상속 길잡이입니다.\n\n가족의 사망 이후 필요한 절차를 확인하도록 도와드리겠습니다.\n\n어떤 내용이 궁금하신가요?",
        "qr": [
            [
                "상속 절차 시작",
                "start"
            ],
            [
                "금융·채무",
                "finance"
            ],
            [
                "상속세",
                "tax"
            ],
            [
                "통신·구독",
                "telecom"
            ],
            [
                "위험 행동 확인",
                "risk"
            ],
            [
                "법령·시행일 확인",
                "law"
            ]
        ]
    },
    "start": {
        "name": "관계 질문",
        "text": "고인과 어떤 관계인가요?",
        "qr": [
            [
                "배우자",
                "rel_spouse"
            ],
            [
                "자녀",
                "rel_child"
            ],
            [
                "부모",
                "rel_parent"
            ],
            [
                "형제자매",
                "rel_sibling"
            ],
            [
                "기타",
                "rel_other"
            ],
            [
                "잘 모르겠어요",
                "rel_unknown"
            ]
        ]
    },
    "rel_spouse": {
        "name": "관계_배우자",
        "text": "배우자는 자녀(직계비속)가 있으면 자녀와, 없으면 부모(직계존속)와 함께 상속인이 됩니다. 둘 다 없으면 배우자 혼자 상속인입니다.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "rel_child": {
        "name": "관계_자녀",
        "text": "자녀(직계비속)는 1순위 상속인입니다. 배우자가 있으면 배우자와 함께 상속받습니다.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "rel_parent": {
        "name": "관계_부모",
        "text": "고인의 부모(직계존속)는 2순위입니다. 고인에게 자녀가 없을 때 상속인이 되며, 배우자가 있으면 함께 상속받습니다.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "rel_sibling": {
        "name": "관계_형제자매",
        "text": "형제자매는 3순위입니다. 고인에게 자녀와 부모가 없고 배우자도 없을 때 상속인이 됩니다.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "rel_other": {
        "name": "관계_기타",
        "text": "4촌 이내 방계혈족 등은 4순위입니다. 앞선 순위 상속인이 없을 때만 상속인이 됩니다. 정확한 순위는 가족관계증명서로 확인해 주세요.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "rel_unknown": {
        "name": "관계_모름",
        "text": "가족관계증명서와 기본증명서로 확인할 수 있습니다. 정부24나 주민센터에서 발급받을 수 있고, 발급 자격은 기관에서 확인해 주세요.\n\n고인이 돌아가신 지 얼마나 되었나요?",
        "qr": [
            [
                "1개월 이내",
                "d1"
            ],
            [
                "1~3개월",
                "d3"
            ],
            [
                "3개월 이상",
                "d6"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "d1": {
        "name": "사망일_1개월이내",
        "text": "사망 후 1개월 이내라면 사망신고 기한이 가장 가깝습니다. 사망신고 때 안심상속 원스톱 서비스를 함께 신청하면 금융·세금 정보를 한 번에 조회할 수 있습니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
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
    "d3": {
        "name": "사망일_1~3개월",
        "text": "사망 후 1~3개월이라면 상속포기·한정승인 판단 기한이 다가옵니다. 먼저 재산과 빚을 조회하고, 판단 전에는 재산을 처분하지 마세요.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
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
    "d6": {
        "name": "사망일_3개월이상",
        "text": "사망 후 3개월이 지났어도 확인할 절차가 남아 있습니다. 상속세 신고와 상속등기를 먼저 확인하세요. 상속포기·한정승인은 기한 이후에 가능한 경우가 있어 전문가 상담을 권합니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "상속세",
                "tax"
            ],
            [
                "법령·시행일 확인",
                "law"
            ],
            [
                "처음으로",
                "welcome"
            ]
        ]
    },
    "finance": {
        "name": "금융·채무",
        "text": "안심상속 원스톱 서비스로 금융기관 예금·대출·보험, 국세·지방세, 자동차, 토지 정보를 한 번에 조회할 수 있습니다. 시·군·구청이나 주민센터, 정부24에서 신청합니다.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
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
    "risk": {
        "name": "위험 행동 확인",
        "text": "상속을 받을지 정하기 전에 고인의 예금을 인출해 쓰거나, 재산을 처분하거나, 빚을 대신 갚으면 상속을 받아들인 것으로 볼 수 있습니다. 장례비 지출 등 판단이 필요한 경우는 전문가에게 확인하세요.\n\n※ 시연용 안내입니다. 공식 기관에서 확인해 주세요.",
        "qr": [
            [
                "금융·채무",
                "finance"
            ],
            [
                "법령·시행일 확인",
                "law"
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
    }
}

HOME = "welcome"
FALLBACK_TEXT = "아직 이해하지 못했어요. 아래 메뉴에서 골라 주세요."


def norm(text: str) -> str:
    return re.sub(r"[\s·.,!?~\-_/()\[\]'\"]", "", text).lower()


# 버튼 문구 -> 이동할 블록
LABELS = {norm(label): target for node in NODES.values() for label, target in node["qr"]}

# 직접 입력한 문장을 연결하는 키워드 (위에서부터 먼저 맞는 것)
KEYWORDS = [
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
                node_id = target
                break
    return node_id


def build(text: str, qr: list) -> dict:
    """카카오 스킬 응답 JSON (version 2.0)을 만듭니다."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": [
                {"label": label, "action": "message", "messageText": label}
                for label, _target in qr
            ],
        },
    }


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/skill")
async def skill(request: Request):
    body = await request.json()
    user_request = body.get("userRequest") or {}
    utterance = (user_request.get("utterance") or "").strip()
    block_name = (user_request.get("block") or {}).get("name", "")

    # 웰컴 블록으로 들어온 첫 진입은 인사말을 돌려줍니다.
    node_id = HOME if "웰컴" in block_name else find_node(utterance)
    print(f"[skill] block={block_name!r} utterance={utterance!r} -> {node_id}", flush=True)

    if node_id is None:
        return build(FALLBACK_TEXT, NODES[HOME]["qr"])
    node = NODES[node_id]
    return build(node["text"], node["qr"])

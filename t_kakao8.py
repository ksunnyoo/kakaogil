import os, sys
os.environ.update(STARTER_KIT_API_URL="", HANDOFF_SERVER_SECRET="s", FRONTEND_ORIGIN="http://localhost:5173")
sys.path.insert(0, ".")
import main
from fastapi.testclient import TestClient
c = TestClient(main.app)
def say(u):
    t = c.post("/skill", json={"userRequest": {"utterance": u, "block": {"name": "블록"}, "user": {"id": "t1"}}}).json()["template"]
    assert 1 <= len(t["outputs"]) <= 3 and len(t["quickReplies"]) <= 10 and all(len(q["label"]) <= 14 for q in t["quickReplies"])
    for o in t["outputs"]:
        if "simpleText" in o: assert len(o["simpleText"]["text"]) <= 1000
        if "textCard" in o:
            tc = o["textCard"]; assert len(tc["title"]) <= 50 and len(tc["description"]) <= 128
            assert 1 <= len(tc["buttons"]) <= 3 and all(len(b["label"]) <= 14 for b in tc["buttons"])
    return t
def urls(t): return [b["webLinkUrl"] for o in t["outputs"] if "textCard" in o for b in o["textCard"]["buttons"]]
say("안녕")
assert urls(say("기본 체크리스트")) == [main.URL_FAMILY_REL, main.URL_DEATH_REPORT, main.URL_ONESTOP_PORTAL]
assert urls(say("법령·시행일 확인")) == [main.URL_CIVIL]
t = say("통신·구독"); assert urls(t) == [main.URL_SKT_DOCS, main.URL_KT_GUIDE] and "직접 확인" in t["outputs"][0]["simpleText"]["text"]
say("특수 상황 목록")
t = say("유류분"); assert urls(t) == [main.URL_EASY_RESERVE, main.URL_CIVIL]
assert "유류분" in [q["label"] for q in say("특수 상황 목록")["quickReplies"]]
for name in ["태아·대습상속", "사실혼·이혼", "혼외자·양자", "상속결격·상실"]:
    assert urls(say(name)) == [main.URL_CIVIL, main.URL_EASY_SHARE, main.URL_EASY_EFFECT], name
assert urls(say("외국인·북한")) == [main.URL_EASY_SHARE, main.URL_EASY_EFFECT]
# 문구를 바꾸지 않았는지(표 내용 미반영) 및 시연용 제거 유지
for k, n in main.NODES.items(): assert "시연용" not in n["text"], k
assert "2026년 3월 17일" not in str(main.NODES)
print("링크 추가 OK")

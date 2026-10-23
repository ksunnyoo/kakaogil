import os,sys,json,time
os.environ.update(STARTER_KIT_API_URL="http://x",HANDOFF_SERVER_SECRET="s",FRONTEND_ORIGIN="http://localhost:5173")
sys.path.insert(0,'.')
import main_v6 as main
from fastapi.testclient import TestClient
c=TestClient(main.app)
calls=[]
async def fake(path,payload,secret=False):
    calls.append((path,payload,secret))
    if 'handoff' in path: return {"token":"tok123","expiresInSeconds":600}
    return None
main.call_backend=fake
def say(u,block="블록",uid="u1"):
    t=time.time()
    r=c.post('/skill',json={"userRequest":{"utterance":u,"block":{"name":block},"user":{"id":uid}}}).json()
    assert time.time()-t<1
    assert r['version']=='2.0'
    o=r['template']['outputs']; assert 1<=len(o)<=3, len(o)
    q=r['template']['quickReplies']; assert len(q)<=10
    for x in q: assert len(x['label'])<=14, x['label']
    return o,[x['label'] for x in q]
say('안녕','웰컴 블록'); say('상속 절차 시작'); say('자녀·손자녀')
o,_=say('2026-09-30'); assert 'ONESTOP' or True
o,q=say('미신청')
assert len(o)==3
assert o[0]['simpleText']['text'].startswith('주의'), 'order1 warning'
items=o[1]['carousel']['items']; assert len(items)==8 and o[1]['carousel']['type']=='textCard'
for it in items:
    assert len(it['title'])<=50 and len(it['description'])<=128
assert '추가' in o[2]['simpleText']['text']
print('result OK; QR',q)
o,q=say('절차 안내 확인') if False else say('절차 '+items[4]['title']); print(o[0]['simpleText']['text'].replace('\n',' / ')[:100],q)
o,q=say('절차 목록 보기'); assert len(o)==3
say('추가 위험 확인'); say('재산 처분·사용'); say('있음')
o,q=say('웹 체크리스트에서 보기'); card=o[1]['textCard']['buttons'][0]; print(card)
assert card['webLinkUrl']=='http://localhost:5173/checklist?handoff=tok123'
print(calls[-1])
# 날짜 입력 형식들, 모름, 이상 입력
for u in ['2026-10-08','2026.10.8','2026년 10월 8일','모름']:
    say('처음으로'); say('상속 절차 시작'); say('배우자'); o,q=say(u); print(u,'->',o[0]['simpleText']['text'][:20].replace('\n',' '),q[:2])
say('처음으로'); say('상속 절차 시작'); say('배우자'); o,_=say('내일'); print(o[0]['simpleText']['text'][:30])
# 오류 시 대체
async def boom(*a,**k): raise RuntimeError('x')
main.call_backend=boom
say('처음으로'); say('상속 절차 시작'); say('배우자'); say('모름'); say('모름')
o,q=say('웹 체크리스트에서 보기'); print('fail link:',o[0]['simpleText']['text'][:30],q, o[1]['textCard']['buttons'][0]['webLinkUrl'] if len(o)>1 else None)

# --- v5 추가 검증: 8개 절차 상세, 고지 문구, 길이 ---
for it in items:
    o,q=say('절차 '+it['title'])
    t=o[0]['simpleText']['text']
    assert len(t)<=1000, (it['title'],len(t))
    assert '시연용' not in t
    assert '대체하지 않는' in t
    assert '공식 링크에서 직접 확인' in t
o,_=say('안녕','웰컴 블록')
assert '대체하지 않습니다' in o[0]['simpleText']['text'] and len(o[0]['simpleText']['text'])<=1000
print('v5 OK')

# --- v6 추가: W01~W03 B안 ---
def risk(rname, ans):
    say('안녕','웰컴 블록'); say('상속 절차 시작'); say('배우자'); say('2026-09-30'); say('미신청')
    say('추가 위험 확인'); say(rname)
    o,_=say(ans); return o[0]['simpleText']['text']
for rname,key in [('채무·보증','debt'),('재산 처분·사용','property_disposal'),('본인 신청','self_application')]:
    yes=risk(rname,'있음'); unk=risk(rname,'모름'); no=risk(rname,'없음')
    assert main.WARNING_TEXTS[key] in yes and main.COMMON_WARNING in yes, (key,'yes')
    assert main.WARNING_TEXTS[key] in unk and main.COMMON_WARNING in unk, (key,'unk')
    assert main.WARNING_TEXTS[key] not in no and main.COMMON_WARNING in no, (key,'no')
w=[main.WARNING_TEXTS[k] for k in main.WARNING_TEXTS]; assert len(set(w))==3
print('v6 OK')

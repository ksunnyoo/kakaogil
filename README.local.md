# 상속 길잡이 카카오 스킬 서버

카카오톡 챗봇 "상속 길잡이"의 스킬 서버입니다. 사용자가 보낸 말(또는 버튼)에 맞춰 상속 절차 안내와 바로연결 버튼을 카카오 스킬 응답 JSON(v2.0)으로 돌려줍니다.

## 구성

| 파일 | 설명 |
| --- | --- |
| `main.py` | FastAPI 스킬 서버. `GET /`(상태 확인), `POST /skill`(카카오 스킬 요청) |
| `requirements.txt` | 의존 패키지 (fastapi, uvicorn) |
| `render.yaml` | Render 배포 설정(참고용) |
| `.github/workflows/keepalive.yml` | 서버 절전 방지용 주기 호출 |

## 안내 흐름

웰컴 → 상속 절차 시작 → 고인과의 관계 선택 → 금융·채무 / 상속세 / 통신·구독 / 위험 행동 확인 / 법령·시행일 확인

직접 입력한 문장은 키워드(예: 대출, 상속세, 해지, 법령)로 해당 안내에 연결하며, 이해하지 못한 말은 메뉴 버튼과 함께 안내 문구를 돌려줍니다.

## 로컬 실행

```bash
uv run --with fastapi --with uvicorn uvicorn main:app --port 8001
curl http://127.0.0.1:8001/
```

## 배포 (Render)

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 서비스 주소: `https://kakaogil.onrender.com`
- 카카오 챗봇 관리자센터 > 스킬의 URL, Test URL: `https://kakaogil.onrender.com/skill`

코드를 수정한 뒤 `git push`하면 Render가 자동으로 다시 배포합니다.

## 운영 시 주의

- 카카오 스킬 응답 제한 시간은 5초입니다. Render 무료 플랜은 15분간 요청이 없으면 절전되어 첫 요청이 늦어지므로, cron-job.org와 GitHub Actions로 10분마다 `/`를 호출합니다.
- 스킬 URL을 바꾸면 스킬을 다시 배포하고, 챗봇 관리자센터에서 전체 배포를 해야 운영 채널에 반영됩니다.
- 사용자가 입력한 말은 서버 로그(`[skill] block=... utterance=...`)에 남습니다. 실제 서비스에서는 로그 보관 정책을 정하세요.
- 안내 내용은 일반 정보이며 법률 자문이 아닙니다. 법령·시행일은 법제처 등 공식 자료로 확인하세요.

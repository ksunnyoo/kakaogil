#!/bin/zsh
# 상속 길잡이 스킬 서버 + 터널 한 번에 실행 (main.py와 같은 폴더에 두세요)
cd "$(dirname "$0")" || exit 1
PORT=8001

# 이미 같은 포트를 쓰는 프로세스 정리
lsof -ti tcp:$PORT | xargs kill 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1

# 종료 시 둘 다 같이 끄기
trap 'kill $SERVER_PID $TUNNEL_PID 2>/dev/null; exit' INT TERM EXIT

# 1) 스킬 서버
uv run --with fastapi --with uvicorn uvicorn main:app --port $PORT > server.log 2>&1 &
SERVER_PID=$!

# 서버 기동 대기 (최대 30초)
for i in {1..30}; do
  curl -s http://127.0.0.1:$PORT/ >/dev/null && break
  sleep 1
done
curl -s http://127.0.0.1:$PORT/ >/dev/null || { echo "서버 시작 실패 → server.log 확인"; exit 1; }
echo "스킬 서버 OK (127.0.0.1:$PORT)"

# 2) 터널
cloudflared tunnel --url http://localhost:$PORT > tunnel.log 2>&1 &
TUNNEL_PID=$!

URL=""
for i in {1..30}; do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "$URL" ] && { echo "터널 주소를 못 찾음 → tunnel.log 확인"; exit 1; }

echo ""
echo "=============================================="
echo " 카카오 스킬 URL / 테스트 URL 에 넣을 주소:"
echo "   $URL/skill"
echo "=============================================="
echo "(이 창을 닫거나 Ctrl+C 하면 서버와 터널이 모두 종료됩니다)"
wait

#!/bin/zsh
# 사용법: ./check.sh https://xxxx.trycloudflare.com
URL=${1:?"터널 주소를 인자로 주세요"}
curl -s -o /dev/null -w "응답시간 %{time_total}초 / HTTP %{http_code}\n" -X POST "$URL/skill" \
  -H "Content-Type: application/json" \
  -d '{"userRequest":{"utterance":"안녕하세요"}}'

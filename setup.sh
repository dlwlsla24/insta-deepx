#!/usr/bin/env bash
# 클론 직후 한 번 실행하면 바로 사용 가능한 상태가 됨.
# 사용법: ./setup.sh

set -euo pipefail

cd "$(dirname "$0")"

echo "==> 1/3 .env 확인"
if [ ! -f .env ]; then
    echo "  .env 가 없습니다. .env.example 을 복사해 키를 채워주세요:"
    echo "    cp .env.example .env"
fi

echo "==> 2/3 Python venv 생성 + 의존성 설치"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "==> 3/3 카드 합성 테스트 (API 불필요)"
python -m src.card_composer

echo ""
echo "✅ 셋업 완료. output/ 에 샘플 카드 7장이 생성됐습니다."
echo "   실제 실행:  source .venv/bin/activate && python -m src.main"
echo "   단계 실행:  STAGE=compose python -m src.main   (검색→요약→카드까지)"

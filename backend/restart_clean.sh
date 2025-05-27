#!/bin/bash

echo "🧹 캐시 정리 중..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

echo "✅ 캐시 정리 완료"
echo "🚀 서버 시작..."

# .env 파일 존재 확인
if [ -f ".env" ]; then
    echo "✅ .env 파일 발견됨"
    if grep -q "ANTHROPIC_API_KEY" .env; then
        echo "✅ ANTHROPIC_API_KEY가 .env 파일에 설정되어 있습니다"
    else
        echo "⚠️  .env 파일에 ANTHROPIC_API_KEY가 없습니다"
    fi
else
    echo "⚠️  .env 파일이 없습니다. ANTHROPIC_API_KEY를 설정해주세요."
fi

# 일반 모드로 실행 (reload 없이)
python main.py

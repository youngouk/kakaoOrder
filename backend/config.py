import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# API 키 설정
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# 판매자 식별 키워드
SELLER_KEYWORDS = [
    "우국상", "신검단", "국민상회", "머슴", "오픈채팅봇", "삐", "마감", "[공지]",
    "판매", "관리자", "대표", "점장", "사장님", "사장", "매니저", "스탭",
    "공구", "공지", "안내", "배송", "입고", "발송", "픽업",
]

# API 설정
API_TITLE = "KakaoOrder API"
API_HOST = "0.0.0.0"
# Use dynamic port (Railway provides PORT env var)
API_PORT = int(os.getenv("PORT", 8000))

import re
import os
import json
import anthropic
import logging
from typing import List, Dict, Any, Set, Tuple, Optional

from config import ANTHROPIC_API_KEY
from services.preprocess_chat import ChatPreprocessor

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Anthropic 클라이언트 초기화
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 채팅 전처리기 초기화
chat_preprocessor = ChatPreprocessor()

# 유효한 Claude 모델 이름 - 3.7 Sonnet으로 업데이트
CLAUDE_MODEL = "claude-3-7-sonnet-20250219"  # 개선된 모델 사용
MAX_RETRY_COUNT = 2  # API 호출 재시도 횟수

# 판매자/관리자 식별을 위한 키워드
SELLER_IDENTIFIERS = {
    "names": [
        "우국상", "신검단", "국민상회", "머슴", "오픈채팅봇", 
        "관리자", "대표", "점장", "사장님", "사장", "매니저", "스탭"
    ],
    "keywords": [
        "삐", "마감", "[공지]", "공지", "안내", "판매", 
        "배송", "입고", "발송", "픽업", "주문", "오늘"
    ]
}


def extract_seller_messages(conversation_text: str) -> List[str]:
    """
    채팅 대화에서 판매자/관리자의 메시지만 추출합니다.
    카카오톡 내보내기 형식에 최적화된 버전입니다.
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        
    Returns:
        List[str]: 판매자 메시지 목록
    """
    lines = conversation_text.split('\n')
    seller_messages = []
    
    current_message = []
    current_speaker = None
    is_seller = False
    date_info = ""
    
    # 현재 카카오톡 내보내기 형식의 메시지 패턴
    # 2025년 4월 26일 오후 12:47, 우국상 신검단 : 총수량을 3개 단위로 주문 부탁드려용! 
    kakao_standard_pattern = r'(\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2}),\s+([^:]+)\s+:\s+(.+)'
    
    # 기존 패턴도 유지 (하위 호환성)
    kakao_alt_pattern = r'^([^:]+):\s+\d{2},\s+([^:]+)\s+:\s+(.+)'
    
    # 사용자 입/퇴장 패턴
    user_action_pattern = r'.+님이 (나갔습니다|들어왔습니다)'
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 표준 카카오톡 패턴 확인
        standard_match = re.match(kakao_standard_pattern, line)
        alt_match = re.match(kakao_alt_pattern, line)
        user_action_match = re.match(user_action_pattern, line)
        
        if standard_match:
            # 이전 메시지 처리
            if current_message and is_seller:
                seller_messages.append('\n'.join(current_message))
            
            # 새 메시지 처리
            date_time, speaker, content = standard_match.groups()
            date_info = date_time
            current_speaker = speaker
            is_seller = _is_seller(speaker)
            current_message = [f"{date_time}, {speaker} : {content}"]
            
        elif alt_match:
            # 이전 메시지 처리
            if current_message and is_seller:
                seller_messages.append('\n'.join(current_message))
            
            # 새 메시지 처리 (대체 형식)
            sender_prefix, speaker, content = alt_match.groups()
            current_speaker = speaker
            is_seller = _is_seller(speaker)
            current_message = [f"{sender_prefix}: {speaker} : {content}"]
            
        elif user_action_match:
            # 사용자 입/퇴장 메시지 처리
            if current_message and is_seller:
                seller_messages.append('\n'.join(current_message))
            current_message = []
            current_speaker = None
            is_seller = False
            
        elif current_speaker and is_seller:
            # 이전 메시지의 연속
            current_message.append(line)
    
    # 마지막 메시지 처리
    if current_message and is_seller:
        seller_messages.append('\n'.join(current_message))
    
    # 결과 로깅
    logger.info(f"총 {len(seller_messages)}개의 판매자 메시지를 추출했습니다.")
    
    # 중복 메시지 제거
    unique_messages = []
    seen = set()
    for msg in seller_messages:
        # 메시지 정규화 (공백 제거 등)
        normalized = ' '.join(msg.split())
        if normalized not in seen:
            seen.add(normalized)
            unique_messages.append(msg)
    
    if len(unique_messages) < len(seller_messages):
        logger.info(f"{len(seller_messages) - len(unique_messages)}개의 중복 메시지가 제거되었습니다.")
    
    return unique_messages

def _is_seller(speaker: str) -> bool:
    """
    발화자가 판매자/관리자인지 확인합니다.
    
    Args:
        speaker (str): 발화자 이름
        
    Returns:
        bool: 판매자이면 True, 아니면 False
    """
    if not speaker:
        return False
    
    # 정규화: 대괄호, 특수문자 제거 및 소문자 변환
    speaker = speaker.strip('[]').lower()
    
    # 명시적인 판매자 계정 목록
    explicit_sellers = [
        "우국상", "신검단", "우국상 신검단", "우국상신검단", 
        "우국상 신검단중앙역점", "우국상중앙역점",
        "국민상회", "국민상회 머슴", "국민상회머슴", 
        "오픈채팅봇", "주문", "판매자"
    ]
    
    # 명시적 판매자 계정 확인
    for seller in explicit_sellers:
        if seller.lower() == speaker.lower():
            return True
    
    # 이름으로 판매자 확인
    for name in SELLER_IDENTIFIERS["names"]:
        if name.lower() in speaker:
            return True
    
    # 키워드로 판매자 확인
    for keyword in SELLER_IDENTIFIERS["keywords"]:
        if keyword.lower() in speaker:
            return True
    
    # 주문 패턴 확인 (숫자 4자리로 시작하거나 끝나는 경우는 고객)
    if re.match(r'^\d{4}', speaker) or re.search(r'\d{4}$', speaker):
        return False
    
    return False

def get_available_products(conversation_text: str) -> Set[str]:
    """
    대화 내용에서 LLM을 활용하여 모든 상품 목록을 추출합니다(품절 포함).
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        
    Returns:
        Set[str]: 모든 상품명 집합 (품절 포함)
    """
    try:
        # 0. 불필요한 메시지 제거 (전처리)
        try:
            logger.info(f"원본 대화 길이: {len(conversation_text)} 문자")
            stats = chat_preprocessor.get_statistics(conversation_text)
            
            logger.info("대화 통계:")
            logger.info(f"  - 전체 메시지: {stats['전체 메시지']}줄")
            logger.info(f"  - 입장/퇴장 메시지: {stats['입장 메시지'] + stats['퇴장 메시지']}줄")
            logger.info(f"  - 삭제된 메시지: {stats['삭제된 메시지']}줄")
            logger.info(f"  - 미디어 메시지: {stats['미디어 메시지']}줄")
            
            # 전처리 실행
            processed_text = chat_preprocessor.preprocess_chat(conversation_text)
            logger.info(f"전처리 후 대화 길이: {len(processed_text)} 문자")
        except Exception as e:
            logger.warning(f"대화 전처리 중 오류 발생: {str(e)}")
            logger.warning("원본 대화로 계속 진행합니다.")
            processed_text = conversation_text
        
        # 1. 판매자/관리자 메시지만 추출
        seller_messages = extract_seller_messages(processed_text)
        logger.info(f"총 {len(seller_messages)}개의 판매자 메시지를 추출했습니다.")
        
        # 판매자 메시지를 하나의 문자열로 결합
        seller_text = "\n\n".join(seller_messages)
        logger.info(f"판매자 메시지 길이: {len(seller_text)} 문자")
        
        # 판매자 메시지만 전달하여 상품 정보 추출
        logger.info("extract_product_info 함수를 사용하여 상품 정보 추출 시작")
        product_info = extract_product_info(conversation_text)  # 이 부분은 내부에서 판매자 메시지를 추출함
        
        # 상품 정보에서 모든 상품 추출 (품절 여부에 상관없이)
        all_products = set()
        for category, products in product_info.items():
            logger.info(f"'{category}' 카테고리에서 {len(products)}개 상품 발견")
            for product in products:
                product_name = product.get("name", "").strip()
                # 유효한 상품명인 경우 추가 (품절 여부에 상관없이)
                if product_name and len(product_name) >= 2:
                    all_products.add(product_name)
        
        logger.info(f"추출된 전체 상품: {len(all_products)}개")
        return all_products
        
    except Exception as e:
        logger.error(f"상품 목록 추출 중 오류 발생: {str(e)}", exc_info=True)
        # 오류 발생 시 빈 세트 반환
        return set()


def extract_products_with_llm(text: str) -> List[Dict[str, Any]]:
    """
    LLM을 사용하여 텍스트에서 판매 상품 목록을 추출합니다.
    
    Args:
        text (str): 분석할 텍스트 (판매자 메시지 또는 전체 대화)
        
    Returns:
        List[Dict[str, Any]]: 추출된 상품 정보 목록
    """
    # 안전을 위한 텍스트 길이 제한
    if len(text) > 50000:
        text = text[:50000] + "...(이하 생략)"
    
    # 함수 호출을 위한 도구 정의
    tools = [{
        "name": "extract_products",
        "description": "대화에서 판매 상품 목록을 추출",
        "input_schema": {
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string", 
                                "description": "상품명"
                            },
                            "sold_out": {
                                "type": "boolean", 
                                "description": "품절/마감 여부"
                            },
                            "quantity": {
                                "type": ["integer", "string", "null"],
                                "description": "수량 정보"
                            }
                        },
                        "required": ["name", "sold_out"]
                    }
                }
            },
            "required": ["products"]
        }
    }]
    
    for retry in range(MAX_RETRY_COUNT + 1):
        try:
            # 시스템 프롬프트 생성 - 가격, 설명 제외하고 품절 상태는 유지
            system_prompt = """
당신은 채팅 대화에서 판매 중인 상품 목록을 추출하는 전문가입니다.
대화 내용을 분석하여 판매 중인 상품 목록(품절된 상품 포함)을 추출해야 합니다.

특히 다음과 같은 패턴에 주목하세요:
1. "🍋🍋🍋레몬 마감 세일🍋🍋🍋 1팩 ➡️ 2900원" - 상품명: 레몬
2. "🌿🌿🌿대파 마감 세일🌿🌿🌿 대파 1단 ➡️ 490원" - 상품명: 대파
3. "☕️☕️☕️아카페라 커피☕️☕️☕️ 4병 ➡️ 3500원" - 상품명: 아카페라 커피
4. "🌈불광동 치즈쫄떡볶이 신상‼️" - 상품명: 불광동 치즈쫄떡볶이
5. "⭐️만다린 14알 1kg 4900원⭐️" - 상품명: 만다린 14알 1kg
6. "❌❌❌오란다 마감❌❌❌" - 상품명: 오란다, 품절: true
7. "
🇰🇷한우국밥 3총사
특가 가즈아‼️‼️

🌈아무거나 고르세요✔️
➡️2팩 6900원‼️
➡️3팩 8900원‼️

✔️한우송화버섯 해장국
🥩진짜 한우 사용
🍄국내산 송화 버섯👍
🍐국내산 무 사용

✔️한우나주곰탕
🥩100% 한우뼈로 국물을👍
🥩한우고기만 사용
🥩100% 고소한 한우꼬들살

✔️한우사골곰탕
🥩100% 한우뼈와 고기만 사용
🥩100% 사골곰탕
🥩100% 고소한 한우 꼬들살👍
" - 상품명: 한우송화버섯 해장국, 한우나주곰탕, 한우사골곰탕 (각각 하나의 상품으로 처리)

특이사항:
- 이모지는 상품명에 포함하지 마세요.
- "마감", "세일", "공지", "판매" 등의 일반적인 단어는 상품명이 아닙니다.
- "❌마감❌", "마감", "품절" 등의 표현이 있는 상품은 sold_out을 true로 설정하세요.
- 가격 정보는 추출하지 마세요.
- 상품 설명은 추출하지 마세요.

반드시 extract_products 도구를 사용하여 결과를 제공하세요. 모든 언급된 상품을 빠짐없이 추출하세요. 품절된 상품도 반드시 포함하세요.
"""

            # 사용자 프롬프트 생성
            user_prompt = f"""
아래 카카오톡 대화 내용에서 판매 중인 모든 상품 목록(품절 포함)을 추출해주세요:

{text}

판매자가 언급한 모든 상품을 최대한 정확하게 추출해주세요.
중복된 상품은 하나로 통합하고, 최신 정보를 유지하세요.
extract_products 도구를 사용하여 결과를 제공해주세요.
"""

            # LLM API 호출 with 도구 사용 (function calling)
            logger.info(f"품목 추출을 위한 LLM API 호출 중... (시도 {retry+1}/{MAX_RETRY_COUNT+1})")
            logger.info(f"입력 텍스트 길이: {len(text)} 자")
            
            response = client.messages.create(
                model=CLAUDE_MODEL,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                tools=tools,
                temperature=1.0,  # thinking 모드에서는 temperature=1.0 필수
                thinking={"type": "enabled", "budget_tokens": 5000},
                max_tokens=10000
            )
            
            # 도구 호출 결과 추출
            result = None
            if response.content and len(response.content) > 0:
                for content_block in response.content:
                    if content_block.type == 'tool_use' and content_block.name == 'extract_products':
                        result = content_block.input
                        break
            
            # 도구 호출 결과가 없는 경우
            if result is None:
                logger.warning("API 응답에서 도구 호출 결과를 찾을 수 없습니다.")
                if retry < MAX_RETRY_COUNT:
                    continue
                return []
            
            # products 필드 확인
            if "products" in result and isinstance(result["products"], list):
                products = result["products"]
                logger.info(f"LLM에서 {len(products)}개 상품 추출 성공")
                return products
            else:
                logger.warning("응답에서 products 필드가 없거나 유효하지 않습니다.")
                if retry < MAX_RETRY_COUNT:
                    continue
                return []
                
        except Exception as e:
            logger.error(f"LLM 추출 중 오류 발생: {str(e)}", exc_info=True)
            if retry < MAX_RETRY_COUNT:
                logger.info(f"재시도 중... ({retry+1}/{MAX_RETRY_COUNT})")
                continue
            else:
                logger.error("모든 재시도 후에도 실패했습니다.")
                return []

def extract_product_info(conversation_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    대화 내용에서 상품 정보를 추출합니다.
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: 상품 정보 목록
    """
    # 전처리: 불필요한 메시지 제거
    try:
        logger.info(f"원본 대화 길이: {len(conversation_text)} 문자")
        # 전처리 실행
        processed_text = chat_preprocessor.preprocess_chat(conversation_text)
        logger.info(f"전처리 후 대화 길이: {len(processed_text)} 문자")
    except Exception as e:
        logger.warning(f"대화 전처리 중 오류 발생: {str(e)}")
        logger.warning("원본 대화로 계속 진행합니다.")
        processed_text = conversation_text
    
    # 판매자 메시지만 추출
    seller_messages = extract_seller_messages(processed_text)
    logger.info(f"추출된 판매자 메시지: {len(seller_messages)}개")
    
    # 판매자 메시지를 하나의 문자열로 결합
    seller_text = "\n\n".join(seller_messages)
    logger.info(f"판매자 메시지 길이: {len(seller_text)} 문자")
    
    # LLM으로 상품 목록 추출 (판매자 메시지만 사용)
    products = extract_products_with_llm(seller_text)
    
    # 단순화된 결과 형식 - 카테고리 구분 없이 단일 목록으로 반환
    result = {"products": []}
    
    for product in products:
        product_name = product.get("name", "").strip()
        if not product_name or len(product_name) < 2:
            continue
        
        # 상품 정보에서 가격과 디스크립션 제외
        result["products"].append({
            "name": product_name,
            "quantity": product.get("quantity"),
            "deadline": "마감" if product.get("sold_out", False) else ""
        })
    
    # 결과 로깅
    logger.info(f"상품 정보 추출 완료: 총 {len(result['products'])}개 상품")
    
    return result
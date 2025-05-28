import os
import json
import re
import anthropic
import datetime
from dotenv import load_dotenv
from typing import Optional, List, Tuple

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def filter_conversation_by_date(
    conversation_text: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    카카오톡 대화 내용을 주어진 날짜 범위로 필터링합니다.
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        start_date (str, optional): 시작 날짜 (형식: "YYYY년 MM월 DD일")
        end_date (str, optional): 종료 날짜 (형식: "YYYY년 MM월 DD일")
        
    Returns:
        str: 필터링된 대화 내용
    """
    print(f"필터링 시작: start_date={start_date}, end_date={end_date}")
    
    # 필터링할 날짜가 없으면 원본 반환
    if not start_date and not end_date:
        return conversation_text
    
    # 날짜 형식 변환 함수
    def parse_korean_date(date_str: str) -> datetime.datetime:
        # "YYYY년 MM월 DD일" 형식을 파싱
        if not date_str:
            return None
        
        pattern = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'
        match = re.match(pattern, date_str)
        if match:
            year, month, day = map(int, match.groups())
            return datetime.datetime(year, month, day)
        return None
    
    # 시작일과 종료일 파싱
    start_datetime = parse_korean_date(start_date) if start_date else None
    end_datetime = parse_korean_date(end_date) if end_date else None
    
    if end_datetime:
        # 종료일은 해당 일자의 끝(23:59:59)까지 포함
        end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
    
    print(f"파싱된 시작 날짜: {start_datetime}, 종료 날짜: {end_datetime}")
    
    # 대화 날짜 추출 및 필터링
    lines = conversation_text.split('\n')
    filtered_lines = []
    current_date = None
    include_block = not start_datetime and not end_datetime  # 초기값: 필터가 없으면 모두 포함
    
    # 카카오톡 날짜 형식 정규식 패턴
    date_pattern = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(오전|오후)\s*(\d{1,2}):(\d{2})'
    
    for line in lines:
        # 날짜 라인인지 확인
        date_match = re.search(date_pattern, line)
        if date_match:
            # 날짜 정보 추출 및 파싱
            year, month, day, ampm, hour, minute = date_match.groups()
            year, month, day = int(year), int(month), int(day)
            hour, minute = int(hour), int(minute)
            
            # 오후인 경우 시간 조정 (오후 3시 -> 15시)
            if ampm == '오후' and hour < 12:
                hour += 12
            
            # datetime 객체 생성
            message_datetime = datetime.datetime(year, month, day, hour, minute)
            
            # 날짜 기준으로 포함 여부 결정
            include_block = True
            if start_datetime and message_datetime < start_datetime:
                include_block = False
            if end_datetime and message_datetime > end_datetime:
                include_block = False
            
            # 현재 날짜 저장
            current_date = message_datetime
        
        # 조건에 맞는 라인만 추가
        if include_block:
            filtered_lines.append(line)
    
    # 필터링 결과 확인
    original_lines = len(lines)
    filtered_count = len(filtered_lines)
    print(f"필터링 결과: 원본 {original_lines}줄 -> 필터링 후 {filtered_count}줄")
    
    # 필터링된 내용이 없는 경우 처리
    if filtered_count == 0:
        print("⚠️ 경고: 지정된 날짜 범위에 해당하는 대화가 없습니다!")
        # 오류 메시지 또는 빈 결과 반환 여부 결정 필요
        # 여기서는 빈 문자열 대신 안내 메시지 반환
        return "지정된 날짜 범위에 해당하는 대화가 없습니다."
    
    return '\n'.join(filtered_lines)

def split_conversation_into_chunks(conversation_text, max_chars=16000):
    """
    대화 내용을 적절한 크기의 청크로 분할합니다.
    
    Args:
        conversation_text (str): 분할할 대화 내용
        max_chars (int): 각 청크의 최대 문자 수
        
    Returns:
        list: 분할된 대화 청크 목록
    """
    lines = conversation_text.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    date_pattern = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(오전|오후)\s*(\d{1,2}):(\d{2})'
    
    for line in lines:
        # 날짜 행인 경우 새로운 청크 시작을 고려
        if re.search(date_pattern, line) and current_length > max_chars/2:  # 더 자주 분할
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_length = 0
        
        current_chunk.append(line)
        current_length += len(line) + 1  # +1 for newline
    
    # 남은 청크 추가
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    # 청크가 없거나 하나만 있으면 최소 2개로 분할
    if len(chunks) <= 1 and len(conversation_text) > max_chars:
        # 더 작은 청크로 분할
        num_chunks = max(2, len(conversation_text) // max_chars + 1)
        chunk_size = len(conversation_text) // num_chunks
        
        chunks = []
        for i in range(num_chunks):
            start_pos = i * chunk_size
            end_pos = start_pos + chunk_size if i < num_chunks - 1 else len(conversation_text)
            
            # 줄바꿈을 찾아서 분할 지점 조정
            if i > 0:
                split_point = conversation_text.find('\n', start_pos)
                if split_point != -1 and split_point < start_pos + 100:  # 100자 이내에 줄바꿈이 있으면
                    start_pos = split_point + 1
            
            if i < num_chunks - 1:
                split_point = conversation_text.rfind('\n', end_pos - 100, end_pos)
                if split_point != -1:  # 끝 부분 100자 이내에 줄바꿈이 있으면
                    end_pos = split_point
            
            chunks.append(conversation_text[start_pos:end_pos])
    
    print(f"대화 내용을 {len(chunks)}개 청크로 분할했습니다.")
    for i, chunk in enumerate(chunks):
        print(f"청크 {i+1} 크기: {len(chunk)} 문자")
    
    return chunks

def merge_analysis_results(results):
    """
    여러 분석 결과를 병합합니다.
    
    Args:
        results (list): 병합할 분석 결과 목록
        
    Returns:
        dict: 병합된 분석 결과
    """
    if not results:
        return {
            "error": "No results to merge",
            "message": "분석할 결과가 없습니다."
        }
    
    # 에러 결과가 있는지 확인
    for result in results:
        if "error" in result:
            print(f"Warning: 일부 분석 결과에 오류가 있습니다: {result.get('message', '알 수 없는 오류')}")
    
    # 결과를 필터링하고 에러가 있는 결과는 제외
    valid_results = [r for r in results if "error" not in r]
    
    if not valid_results:
        return {
            "error": "All analyses failed",
            "message": "모든 분석이 실패했습니다."
        }
    
    # 결과 병합을 위한 초기 구조 설정
    merged = {
        "time_based_orders": [],
        "item_based_summary": [],
        "customer_based_orders": [],
        "table_summary": {
            "headers": [],
            "rows": [],
            "required_quantities": []
        }
    }
    
    # 시간순 주문 내역 병합
    for result in valid_results:
        if "time_based_orders" in result and result["time_based_orders"]:
            merged["time_based_orders"].extend(result["time_based_orders"])
    
    # 시간 정렬
    if merged["time_based_orders"]:
        merged["time_based_orders"].sort(key=lambda x: x.get("time", ""))
    
    # 품목별 요약 병합 - 같은 품목은 수량 합산
    item_map = {}
    for result in valid_results:
        if "item_based_summary" in result and result["item_based_summary"]:
            for item_summary in result["item_based_summary"]:
                item_name = item_summary.get("item", "")
                if not item_name:
                    continue
                
                if item_name in item_map:
                    # 기존 항목 업데이트
                    try:
                        total1 = int(item_map[item_name]["total_quantity"])
                        total2 = int(item_summary.get("total_quantity", "0"))
                        item_map[item_name]["total_quantity"] = str(total1 + total2)
                    except ValueError:
                        # 숫자로 변환할 수 없는 경우
                        pass
                    
                    # 주문자 목록 병합
                    customers1 = item_map[item_name]["customers"]
                    customers2 = item_summary.get("customers", "")
                    if customers1 and customers2:
                        item_map[item_name]["customers"] = f"{customers1}, {customers2}"
                    elif customers2:
                        item_map[item_name]["customers"] = customers2
                else:
                    # 새 항목 추가
                    item_map[item_name] = item_summary
    
    merged["item_based_summary"] = list(item_map.values())
    
    # 주문자별 주문 내역 병합 - 같은 주문자의 같은 품목은 수량 합산
    customer_item_map = {}
    for result in valid_results:
        if "customer_based_orders" in result and result["customer_based_orders"]:
            for order in result["customer_based_orders"]:
                customer = order.get("customer", "")
                item = order.get("item", "")
                key = f"{customer}:{item}"
                
                if not customer or not item:
                    continue
                
                if key in customer_item_map:
                    # 기존 항목 업데이트
                    try:
                        qty1 = int(customer_item_map[key]["quantity"])
                        qty2 = int(order.get("quantity", "0"))
                        customer_item_map[key]["quantity"] = str(qty1 + qty2)
                    except ValueError:
                        # 숫자로 변환할 수 없는 경우
                        pass
                    
                    # 비고는 첫 번째 항목만 유지
                else:
                    # 새 항목 추가
                    customer_item_map[key] = order
    
    merged["customer_based_orders"] = list(customer_item_map.values())
    
    # 교차표 병합 - 모든 주문자와 품목을 수집한 후 새로 구성
    all_headers = set()
    customer_item_quantities = {}
    
    for result in valid_results:
        if "table_summary" not in result or not result["table_summary"]:
            continue
            
        # 헤더(품목) 수집
        if "headers" in result["table_summary"] and result["table_summary"]["headers"]:
            all_headers.update(result["table_summary"]["headers"])
        
        # 주문자별 품목 수량 수집
        if "rows" in result["table_summary"] and result["table_summary"]["rows"]:
            for row in result["table_summary"]["rows"]:
                customer = row.get("customer", "")
                if not customer or not isinstance(row.get("items"), list):
                    continue
                
                if customer not in customer_item_quantities:
                    customer_item_quantities[customer] = {}
                
                # 현재 행의 헤더와 items 매핑
                headers = result["table_summary"]["headers"]
                items = row["items"]
                
                for i, qty in enumerate(items):
                    if i < len(headers):
                        item = headers[i]
                        # 숫자로 변환 가능한지 확인
                        try:
                            if qty and str(qty).strip():
                                qty_value = int(qty)
                                if item in customer_item_quantities[customer]:
                                    customer_item_quantities[customer][item] += qty_value
                                else:
                                    customer_item_quantities[customer][item] = qty_value
                        except (ValueError, TypeError):
                            pass
    
    # 교차표 재구성
    all_headers = sorted(list(all_headers))
    merged["table_summary"]["headers"] = all_headers
    
    # 주문자별 행 구성
    for customer, items in customer_item_quantities.items():
        row_items = []
        for header in all_headers:
            row_items.append(items.get(header, ""))
        
        merged["table_summary"]["rows"].append({
            "customer": customer,
            "items": row_items
        })
    
    # 품목별 총 필요 수량 계산
    required_quantities = []
    for header in all_headers:
        total = 0
        for customer, items in customer_item_quantities.items():
            if header in items and isinstance(items[header], (int, float)):
                total += items[header]
        required_quantities.append(total if total > 0 else "")
    
    merged["table_summary"]["required_quantities"] = required_quantities
    
    return merged

def analyze_conversation(conversation_text, start_date=None, end_date=None, shop_name=None):
    """
    Analyze the conversation using Claude 3.7 Sonnet with thinking enabled
    
    Args:
        conversation_text (str): The KakaoTalk conversation text
        start_date (str, optional): Start date to filter the conversation (format: "YYYY년 MM월 DD일")
        end_date (str, optional): End date to filter the conversation (format: "YYYY년 MM월 DD일")
        shop_name (str, optional): Name of the shop/chat
        
    Returns:
        dict: The analyzed data including time-based orders, item summaries, and customer summaries
    """
    print(f"Starting analysis: shop_name={shop_name}, start_date={start_date}, end_date={end_date}")
    print(f"Conversation length: {len(conversation_text)} characters")
    
    # 날짜 기반 필터링 적용 (코드 기반 전처리)
    filtered_conversation = filter_conversation_by_date(
        conversation_text=conversation_text,
        start_date=start_date,
        end_date=end_date
    )
    
    # 필터링 결과 확인
    if filtered_conversation == "지정된 날짜 범위에 해당하는 대화가 없습니다.":
        return {
            "error": "No data",
            "message": "지정된 날짜 범위에 해당하는 대화가 없습니다."
        }
    
    print(f"Filtered conversation length: {len(filtered_conversation)} characters")
    
    # 대화 내용이 너무 길면 청크로 분할 - 청크 크기 줄임
    MAX_CHUNK_SIZE = 16000  # 약 16KB로 제한
    if len(filtered_conversation) > MAX_CHUNK_SIZE:
        chunks = split_conversation_into_chunks(filtered_conversation, MAX_CHUNK_SIZE)
        print(f"대화를 {len(chunks)}개 청크로 분할했습니다.")
        
        # 각 청크별로 분석 수행
        results = []
        for i, chunk in enumerate(chunks):
            print(f"청크 {i+1}/{len(chunks)} 분석 중... ({len(chunk)} 문자)")
            # 각 청크 별로 분석 수행
            chunk_result = analyze_conversation_chunk(chunk, start_date, end_date, shop_name)
            results.append(chunk_result)
        
        # 분석 결과 병합
        return merge_analysis_results(results)
    else:
        # 단일 청크 분석
        return analyze_conversation_chunk(filtered_conversation, start_date, end_date, shop_name)

def analyze_conversation_chunk(conversation_text, start_date=None, end_date=None, shop_name=None):
    """
    단일 대화 청크를 분석합니다.
    
    Args:
        conversation_text (str): 분석할 대화 청크
        start_date, end_date, shop_name: 원래 함수와 동일
        
    Returns:
        dict: 분석 결과
    """
    # Create the system prompt
    system_prompt = """
 당신은 카카오톡 대화 내역을 분석하여 주문 정보를 정확하게 추출하는 전문가입니다. 다음 지침에 따라 철저하게 분석해주세요:

## 대화 분석 규칙
1. 대화에서 날짜 정보는 '2025년 1월 23일'과 같은 형식으로 표시됩니다. 해당 날짜를 기준으로 대화를 분리하세요.
2. 주문 형식은 반드시 명시적으로 "[닉네임/ID] [상품명] [수량]" 패턴으로 나타난 경우만 주문으로 인식합니다. (예: "별1367 동그랑땡1", "세자매네💜/0601 감자전 2")
3. 다른 형식의 메시지는 주문으로 인식하지 않습니다.
4. 주문자는 닉네임 또는 닉네임과 ID 조합으로 식별됩니다. (예: "슈팡이6497", "세자매네💜/0601")
5. 비고란에는 픽업 일자, 특이사항, 취소 여부 등이 포함될 수 있습니다.
6. 주문 취소는 "[닉네임/ID] [상품명] [수량] 취소" 형식을 따랐을 때만 취소로 인식합니다.
7. 마감 안내는 "❌️마감❌️" 형태로 표시됩니다.

## 정보 추출 방법
1. 주문 메시지에서는 다음 정보를 추출하세요:
   - 시간: 메시지 발송 시간
   - 주문자: 닉네임/ID
   - 품목: 주문한 상품명
   - 수량: 주문 수량 (기본값은 1개)
   - 비고: 특이사항 (픽업일, 취소여부, 변경사항 등)

2. 주문 메시지에 여러 품목이 포함된 경우 각 품목별로 분리하여 기록하세요. (예: "하하네 0910 : 절편2 꿀떡 1" → 두 개의 주문으로 분리)

3. 점주나 스탭이 보낸 공지, 마감 안내 등은 주문으로 간주하지 마세요.

4. 주문 취소나 변경 시 기존 주문을 찾아 상태를 업데이트하세요.

## 결과 출력 형식
분석 결과는 다음 네 가지 형태로 정리하세요:

1. 시간순 주문 내역: 주문이 들어온 시간 순서로 정렬
   - 시간, 주문자, 품목, 수량, 비고 포함

2. 품목별 총 주문 갯수:
   - 품목명, 총 수량, 해당 품목을 주문한 주문자 목록(수량 포함) 표시

3. 주문자별 주문 내역:
   - 주문자, 품목, 수량, 비고 포함
   - 주문자가 여러 품목을 주문한 경우 각각 별도 행으로 표시
   - 비고는 해당 주문자의 첫 번째 항목에만 표시

4. 주문자-상품 교차표:
   - 행: 주문자
   - 열: 상품명
   - 각 셀: 해당 주문자가 주문한 해당 상품의 수량
   - 마지막 행에는 각 상품별 총 필요 수량 표시
   - 주문자가 상품을 주문하지 않은 경우 빈칸으로 표시
    """
    
    # Create the user prompt with instructions
    date_guidance = ""
    if start_date and end_date:
        date_guidance = f"\n기간 제한: {start_date}부터 {end_date}까지의 대화만 분석해주세요."
    elif start_date:
        date_guidance = f"\n기간 제한: {start_date}부터의 대화만 분석해주세요."
    elif end_date:
        date_guidance = f"\n기간 제한: {end_date}까지의 대화만 분석해주세요."
        
    shop_context = f"\n이 대화는 '{shop_name}' 상점의 주문 내역입니다." if shop_name else ""
    
    user_prompt = f"""
    아래 KakaoTalk 대화 내역을 분석하여 주문 정보를 추출해주세요.{date_guidance}{shop_context}
    
    분석 결과는 다음 4가지 테이블로 구성해주세요:
    
    1. 시간순 주문 내역: 대화에서 언급된 모든 주문을 시간 순서대로 정리
       - 시간, 주문자, 품목, 수량, 비고 포함
       
    2. 품목별 총 주문 갯수: 각 품목별 총 주문량 정리
       - 품목명, 총 수량, 주문자 목록 포함
       
    3. 주문자별 주문 내역: 주문자 기준으로 주문 내용 정리
       - 주문자, 품목, 수량, 비고 포함
       - 주문자가 복수의 품목을 주문한 경우 각각 별도 행으로 표시
       - 비고는 해당 주문자의 첫 번째 항목에만 표시
       
    4. 주문자-상품 교차표: 주문자와 상품을 축으로 하는 테이블
       - 행: 주문자, 열: 상품명
       - 각 셀: 해당 주문자가 주문한 해당 상품의 수량
       - 마지막 행에는 총 필요수량 표시
       
    반드시 JSON 형식으로 응답해주세요. 응답 형식은 다음과 같습니다:
    
    ```json
    {{
      "time_based_orders": [
        {{
          "time": "시간",
          "customer": "주문자",
          "item": "품목",
          "quantity": "수량",
          "note": "비고"
        }}
      ],
      "item_based_summary": [
        {{
          "item": "품목명",
          "total_quantity": "총 수량",
          "customers": "주문자 목록"
        }}
      ],
      "customer_based_orders": [
        {{
          "customer": "주문자명",
          "item": "품목명",
          "quantity": "수량",
          "note": "비고"
        }}
      ],
      "table_summary": {{
        "headers": ["상품명1", "상품명2", ...],
        "rows": [
          {{
            "customer": "주문자명1",
            "items": [수량1, 수량2, ...]
          }},
          ...
        ],
        "required_quantities": [총수량1, 총수량2, ...]
      }}
    }}
    ```
    
    대화내역:
    ```
    {conversation_text}
    ```
    """
    
    try:
        # Thinking 모드 활성화 (원래 의도대로)
        print("Calling Claude API with thinking mode enabled...")
        thinking_budget = 5000
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=8000,  # 토큰 수 제한
            system=system_prompt,
            temperature=1.0,  # Thinking 모드에서는 반드시 temperature=1 설정 필요
            thinking={"type": "enabled", "budget_tokens": thinking_budget},
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        print("API call completed successfully with thinking mode")
        
        # 응답 객체 구조 디버깅 (상세)
        print(f"Response type: {type(response)}")
        print(f"Response attributes: {dir(response)}")
        
        # Anthropic API의 응답 구조에 따라 정확하게 추출
        try:
            print("Response content structure:", response.content)
            
            # 응답에서 텍스트 콘텐츠 찾기
            content = None
            
            # 응답 구조 확인
            if hasattr(response, 'content') and response.content:
                # 콘텐츠가 리스트인 경우 (일반적인 경우)
                if isinstance(response.content, list):
                    for item in response.content:
                        if hasattr(item, 'text') and item.text:
                            content = item.text
                            break
                        elif hasattr(item, 'value') and item.value:  # 일부 ThinkingBlock 객체는 value 속성을 가짐
                            content = item.value
                            break
                        elif isinstance(item, str):
                            content = item
                            break
                        else:
                            print(f"Content item type: {type(item)}")
                            print(f"Content item attributes: {dir(item)}")
                            # ThinkingBlock 등 특수 객체 처리
                            try:
                                content = item.__str__()  # __str__ 메서드 시도
                            except:
                                content = repr(item)  # repr() 대체 방법
                
                # 콘텐츠가, dict 또는 문자열인 경우
                elif isinstance(response.content, (dict, str)):
                    content = str(response.content)
            
            # 콘텐츠를 찾지 못한 경우 전체 응답을 문자열로 변환
            if content is None:
                print("Could not extract content normally, using full response...")
                # 모든 응답의 문자열 표현 시도
                if hasattr(response, 'model_dump_json'):
                    content = response.model_dump_json()  # Pydantic 모델인 경우
                else:
                    content = str(response)
            
            print(f"Extracted content: {content[:100]}...")  # 처음 100자만 로깅
            
            # 콘텐츠가 정상적으로 추출되었는지 확인
            if not content:
                return {"error": "No content extracted from response", "response_info": str(response)[:500]}
            
            # JSON 파싱 시도 - 개선된 방식
            try:
                # JSON 구조를 찾기 위한 개선된 패턴 매칭
                # 1. 먼저 코드 블록 검색
                json_str = ""
                json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(1)
                    print("Found JSON block in markdown code block")
                else:
                    # 2. 중괄호로 둘러싸인 구조 검색
                    if content.strip().startswith('{') and content.strip().endswith('}'):
                        json_str = content.strip()
                        print("Found JSON-like structure in entire content")
                    else:
                        # 3. 복잡한 패턴 매칭으로 JSON 구조 찾기
                        print("Searching for JSON-like structure in content...")
                        # 더 정확한 JSON 패턴 매칭
                        json_pattern = r'(\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\})'
                        matches = re.findall(json_pattern, content)
                        
                        if matches:
                            # 가장 긴 매치를 선택 (완전한 JSON일 가능성이 높음)
                            json_str = max(matches, key=len)
                            print(f"Found potential JSON structure (length: {len(json_str)})")
                        else:
                            # 4. 마지막 수단: 줄 단위로 JSON 찾기
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.startswith('{') and line.endswith('}'):
                                    if len(line) > len(json_str):
                                        json_str = line
                            
                            if json_str:
                                print(f"Found JSON in line-by-line search (length: {len(json_str)})")
                            else:
                                print("No JSON structure found")
                                json_str = content
                
                # 정리 및 불필요한 문자 제거
                json_str = json_str.replace('```', '').strip()
                
                # 특수 문자 처리 (일반적인 JSON 파싱 오류 원인)
                # 유니코드 이스케이프 문자 처리
                json_str = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), json_str)
                # 잘못된 이스케이프 문자 제거
                json_str = re.sub(r'\\([^"\\/bfnrtu])', r'\1', json_str)
                
                print(f"Cleaned JSON string length: {len(json_str)}")
                print(f"JSON string start: {json_str[:100]}...")
                
                try:
                    # 실제 JSON 파싱
                    result = json.loads(json_str)
                    print("JSON parsing successful")
                    return result
                except json.JSONDecodeError as parse_error:
                    # 구체적인 파싱 오류 처리
                    print(f"Initial JSON parse error: {str(parse_error)}")
                    
                    # 문제가 되는 문자 위치 확인
                    error_pos = parse_error.pos
                    context_start = max(0, error_pos - 50)
                    context_end = min(len(json_str), error_pos + 50)
                    error_context = json_str[context_start:context_end]
                    
                    print(f"Error context around position {error_pos}: ...{error_context}...")
                    
                    # 가능한 오류 수정 시도
                    # 1. 누락된 따옴표 문제
                    if "Expecting '\"'" in str(parse_error) or "Expecting property name" in str(parse_error):
                        # 속성 이름 주변에 누락된 따옴표 추가 시도
                        fixed_str = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_str)
                        try:
                            result = json.loads(fixed_str)
                            print("JSON parsing successful after fixing missing quotes")
                            return result
                        except:
                            pass
                    
                    # 2. 트레일링 쉼표 문제
                    if "Expecting ',' delimiter" in str(parse_error):
                        # 쉼표 주변 오류 수정 시도
                        fixed_str = re.sub(r',\s*}', '}', json_str)
                        fixed_str = re.sub(r',\s*]', ']', fixed_str)
                        try:
                            result = json.loads(fixed_str)
                            print("JSON parsing successful after fixing trailing commas")
                            return result
                        except:
                            pass
                    
                    # 3. 특수 JSON 라이브러리 시도 (hjson)
                    try:
                        import hjson
                        result = hjson.loads(json_str)
                        print("JSON parsing successful using hjson")
                        return result
                    except (ImportError, Exception):
                        print("hjson library not available or parsing failed")
                    
                    # 4. 최후의 수단: 부분 파싱
                    try:
                        # 객체 내부의 개별 속성 추출 시도
                        property_pattern = r'"([^"]+)"\s*:\s*(\[[^\]]*\]|\{[^}]*\}|"[^"]*"|[^,}\]]*)'
                        properties = re.findall(property_pattern, json_str)
                        
                        result = {}
                        for prop_name, prop_value in properties:
                            try:
                                # 값 정리 및 파싱 시도
                                value = prop_value.strip()
                                if value.startswith('"') and value.endswith('"'):
                                    # 문자열
                                    result[prop_name] = value[1:-1]
                                elif value.startswith('[') and value.endswith(']'):
                                    # 배열
                                    try:
                                        result[prop_name] = json.loads(value)
                                    except:
                                        result[prop_name] = []
                                elif value.startswith('{') and value.endswith('}'):
                                    # 객체
                                    try:
                                        result[prop_name] = json.loads(value)
                                    except:
                                        result[prop_name] = {}
                                else:
                                    # 기타 값 (숫자, 불리언, null 등)
                                    if value.lower() == 'true':
                                        result[prop_name] = True
                                    elif value.lower() == 'false':
                                        result[prop_name] = False
                                    elif value.lower() == 'null':
                                        result[prop_name] = None
                                    else:
                                        try:
                                            result[prop_name] = float(value) if '.' in value else int(value)
                                        except:
                                            result[prop_name] = value
                            except Exception as prop_error:
                                print(f"Error parsing property {prop_name}: {str(prop_error)}")
                        
                        if result:
                            print("Partial JSON parsing successful")
                            return result
                    except Exception as partial_error:
                        print(f"Partial parsing failed: {str(partial_error)}")
                
                # 빈 결과 구조 생성
                print("All JSON parsing attempts failed, returning empty structure")
                return {
                    "time_based_orders": [],
                    "item_based_summary": [],
                    "customer_based_orders": [],
                    "table_summary": {
                        "headers": [],
                        "rows": [],
                        "required_quantities": []
                    },
                    "error": "JSON parsing failed",
                    "message": str(parse_error)
                }
            
            except Exception as e:
                print(f"Unexpected error during JSON handling: {str(e)}")
                # 빈 결과 구조 생성
                return {
                    "time_based_orders": [],
                    "item_based_summary": [],
                    "customer_based_orders": [],
                    "table_summary": {
                        "headers": [],
                        "rows": [],
                        "required_quantities": []
                    },
                    "error": "Unexpected error",
                    "message": str(e)
                }
        except Exception as extract_error:
            return {"error": "Response content extraction failed", "message": str(extract_error), "response_info": str(response)[:500]}
    
    except Exception as e:
        # 자세한 예외 정보와 추적을 위한 로깅
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error occurred: {str(e)}")
        print(f"Traceback: {error_trace}")
        
        # 에러 상세 정보 반환
        return {
            "error": "API call failed", 
            "message": str(e),
            "traceback": error_trace[:500] if error_trace else None
        }

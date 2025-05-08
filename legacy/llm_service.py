import os
import json
import re
import anthropic
import datetime
import concurrent.futures
from dotenv import load_dotenv
from typing import Optional, List, Tuple, Dict, Any, Set

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 판매자 식별 키워드
SELLER_KEYWORDS = [
    "우국상", "신검단", "국민상회", "머슴", "오픈채팅봇", "삐", "마감", "[공지]",
    "판매", "관리자", "대표", "점장", "사장님", "사장", "매니저", "스탭",
    "공구", "공지", "안내", "배송", "입고", "발송", "픽업",
    # 특정 판매자 닉네임 (실제 대화에서 발견된 패턴)
    "우국상 신검단", "우국상신검단", "검단점", "국민상회 머슴"
]

# 상품 카테고리와 정규식 패턴
PRODUCT_CATEGORIES = {
    "곰탕": [
        r'한우진국곰탕', r'한우사골곰탕', r'한우나주곰탕', r'곰탕', r'국밥', r'해장국',
        r'송화버섯\s*(?:해장국|국|곰탕)', r'사골(?:국|곰탕)?', r'우국밥', r'국밥\s*3총사'
    ],
    "불고기": [
        r'광양(?:한돈)?불고기', r'불고기\s*\d*(?:세트|팩)?', r'한돈(?:광양)?불고기',
        r'치즈부대찌개', r'한가득\s*치즈부대찌개'
    ],
    "오란다": [
        r'(?:돌리|엄마가)오란다', r'오란다', r'조청오란다', r'감태오란다', r'견과오란다'
    ],
    "케이크": [
        r'(?:초코|고구마)(?:생크림)?케이?[크익]', r'생크림\s*케이크', 
        r'케이크', r'케익'
    ],
    "마스크팩": [
        r'하이드로겔\s*(?:마스크팩|시트)', r'마스크팩', r'프리미엄\s*하이드로겔\s*시트',
        r'하이드로겔', r'프리미엄\s*(?:마스크팩|시트)'
    ],
    "샤베트": [
        r'(?:애플망고|망고|샤인머스캣|샤인|요구르트)\s*샤베[트|드]',
        r'샤베[트|드]'
    ],
    "파닭": [
        r'(?:파|치킨|네네)(?:닭)?꼬치', r'파닭꼬치', r'파닭', r'치킨꼬치'
    ],
    "식빵": [
        r'(?:도제|탕종)(?:우유|통밀)?식빵', r'식빵', r'도제식빵', r'우유식빵'
    ],
    "크림": [
        r'(?:아미노\s*퍼밍|아하바하파하|세레스킨|미라클)?\s*크림',
        r'퍼밍크림', r'아미노크림'
    ],
    "건강식품": [
        r'침향환', r'발효침향환', r'알부민', r'홍삼', r'석류',
        r'(?:프리미엄)?발효환', r'동안석류', r'석류한알', r'소비기한'
    ]
}

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

def split_conversation_into_chunks(conversation_text: str, max_chunk_size: int = 16000) -> List[str]:
    """
    Split a long conversation into smaller chunks for processing
    """
    chunks = []
    current_chunk = ""
    lines = conversation_text.split("\n")
    
    for i, line in enumerate(lines):
        if len(current_chunk) + len(line) + 1 <= max_chunk_size:
            current_chunk += line + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line + "\n"
        
        if i == len(lines) - 1 and current_chunk:
            chunks.append(current_chunk)
    
    print(f"대화 내용을 {len(chunks)}개 청크로 분할했습니다.")
    for i, chunk in enumerate(chunks):
        print(f"청크 {i+1} 크기: {len(chunk)} 문자")
        print(f"청크 {i+1} 내용 미리보기: {chunk[:100]}...")
    
    return chunks

def merge_analysis_results(results):
    """
    병렬 처리된 분석 결과를 병합합니다.
    
    Args:
        results (list): 분석 결과 리스트
        
    Returns:
        dict: 병합된 결과
    """
    merged_result = {
        "available_products": [],  # 판매 물품 정의 리스트
        "time_based_orders": [],
        "item_based_summary": {},  # 딕셔너리로 임시 저장
        "customer_based_orders": [],
        "table_summary": {
            "headers": set(),  # 중복 제거를 위해 set 사용
            "rows": {},  # 고객별 주문 품목을 딕셔너리로 임시 저장
            "required_quantities": {}  # 품목별 필요 수량을 딕셔너리로 임시 저장
        },
        "order_pattern_analysis": {
            "hourly_orders": {},  # 시간대별 주문 수를 딕셔너리로 임시 저장
            "popular_items": {},  # 품목별 인기도를 딕셔너리로 임시 저장
            "sold_out_items": set()  # 품절 품목을 set으로 임시 저장
        }
    }
    
    # 판매 물품 정의 병합을 위한 맵
    available_products_map = {}
    
    # 각 결과를 병합
    valid_results_count = 0
    error_results_count = 0
    
    for result in results:
        # 에러 정보가 있는지 확인
        has_error = "error" in result and result["error"]
        
        if has_error:
            error_results_count += 1
            print(f"⚠️ 에러가 있는 청크 감지: {result.get('message', result.get('error', '알 수 없는 오류'))}")
        else:
            valid_results_count += 1
        
        # 0. available_products 병합
        if "available_products" in result and isinstance(result["available_products"], list):
            products_count_before = len(available_products_map)
            
            for product in result["available_products"]:
                product_name = product.get("name", "")
                if not product_name:
                    continue
                
                # 이미 있는 상품이면 정보 보강
                if product_name in available_products_map:
                    existing_product = available_products_map[product_name]
                    
                    # 가격 정보 업데이트 (없는 경우에만)
                    if not existing_product.get("price") and product.get("price"):
                        existing_product["price"] = product["price"]
                    
                    # 카테고리 업데이트 (없는 경우에만)
                    if not existing_product.get("category") and product.get("category"):
                        existing_product["category"] = product["category"]
                    
                    # 수령일 업데이트 (없는 경우에만)
                    if not existing_product.get("delivery_date") and product.get("delivery_date"):
                        existing_product["delivery_date"] = product["delivery_date"]
                    
                    # 마감 정보 업데이트 (없는 경우에만)
                    if not existing_product.get("deadline") and product.get("deadline"):
                        existing_product["deadline"] = product["deadline"]
                else:
                    # 새 상품 추가
                    available_products_map[product_name] = product.copy()
            
            products_count_after = len(available_products_map)
            if products_count_after > products_count_before:
                print(f"available_products: {products_count_after-products_count_before}개 상품 병합됨 (총 {products_count_after}개)")
        
        # 1. time_based_orders 병합
        if "time_based_orders" in result and isinstance(result["time_based_orders"], list):
            orders_count_before = len(merged_result["time_based_orders"])
            merged_result["time_based_orders"].extend(result["time_based_orders"])
            orders_count_after = len(merged_result["time_based_orders"])
            
            if orders_count_after > orders_count_before:
                print(f"time_based_orders: {orders_count_after-orders_count_before}개 주문 병합됨 (총 {orders_count_after}개)")
        
        # 2. item_based_summary 병합
        if "item_based_summary" in result and isinstance(result["item_based_summary"], list):
            for item in result["item_based_summary"]:
                item_name = item.get("item", "")
                if not item_name:
                    continue
                
                if item_name not in merged_result["item_based_summary"]:
                    merged_result["item_based_summary"][item_name] = item
                else:
                    # 기존 항목에 정보 병합
                    existing_item = merged_result["item_based_summary"][item_name]
                    
                    # 수량 합산
                    try:
                        existing_qty = int(existing_item.get("total_quantity", "0") or "0")
                        new_qty = int(item.get("total_quantity", "0") or "0")
                        existing_item["total_quantity"] = str(existing_qty + new_qty)
                    except (ValueError, TypeError):
                        # 숫자 변환 실패 시 문자열 그대로 유지
                        pass
                    
                    # 고객 목록 병합
                    existing_customers = existing_item.get("customers", "")
                    new_customers = item.get("customers", "")
                    if existing_customers and new_customers:
                        existing_item["customers"] = f"{existing_customers}, {new_customers}"
                    elif new_customers:
                        existing_item["customers"] = new_customers
                    
                    # 카테고리 설정 (비어있는 경우에만)
                    if not existing_item.get("category") and item.get("category"):
                        existing_item["category"] = item.get("category")
                    
                    # 수령일 설정 (비어있는 경우에만)
                    if not existing_item.get("delivery_date") and item.get("delivery_date"):
                        existing_item["delivery_date"] = item.get("delivery_date")
        
        # 3. customer_based_orders 병합
        if "customer_based_orders" in result and isinstance(result["customer_based_orders"], list):
            orders_count_before = len(merged_result["customer_based_orders"])
            merged_result["customer_based_orders"].extend(result["customer_based_orders"])
            orders_count_after = len(merged_result["customer_based_orders"])
            
            if orders_count_after > orders_count_before:
                print(f"customer_based_orders: {orders_count_after-orders_count_before}개 주문 병합됨 (총 {orders_count_after}개)")
        
        # 4. table_summary 병합
        if "table_summary" in result and isinstance(result["table_summary"], dict):
            # 헤더 (상품명) 병합
            if "headers" in result["table_summary"] and isinstance(result["table_summary"]["headers"], list):
                merged_result["table_summary"]["headers"].update(result["table_summary"]["headers"])
            
            # 행 (주문자별 상품 수량) 병합
            if "rows" in result["table_summary"] and isinstance(result["table_summary"]["rows"], list):
                for row in result["table_summary"]["rows"]:
                    customer = row.get("customer", "")
                    if not customer:
                        continue

                    items = row.get("items", [])
                    if not isinstance(items, list):
                        continue

                    headers = result["table_summary"].get("headers", [])
                    for i, item_quantity in enumerate(items):
                        if i < len(headers):
                            item_name = headers[i]
                            # 기존 수량 + 새 수량
                            if item_name in merged_result["table_summary"]["rows"][customer]:
                                try:
                                    existing_qty = merged_result["table_summary"]["rows"][customer][item_name]
                                    if existing_qty and item_quantity:
                                        merged_result["table_summary"]["rows"][customer][item_name] = \
                                            str(int(existing_qty) + int(item_quantity))
                                except (ValueError, TypeError):
                                    merged_result["table_summary"]["rows"][customer][item_name] = item_quantity
                            else:
                                merged_result["table_summary"]["rows"][customer][item_name] = item_quantity
            
            # 필요 수량 병합
            if "required_quantities" in result["table_summary"] and isinstance(result["table_summary"]["required_quantities"], list):
                headers = result["table_summary"].get("headers", [])
                quantities = result["table_summary"].get("required_quantities", [])
                
                for i, qty in enumerate(quantities):
                    if i < len(headers):
                        item_name = headers[i]
                        
                        if item_name in merged_result["table_summary"]["required_quantities"]:
                            try:
                                # 문자열을 숫자로 변환 후 합산하고 다시 문자열로
                                existing_qty = int(merged_result["table_summary"]["required_quantities"][item_name] or "0")
                                new_qty = int(qty or "0")
                                merged_result["table_summary"]["required_quantities"][item_name] = str(existing_qty + new_qty)
                        except (ValueError, TypeError):
                                # 변환 실패 시 그대로 유지
                                pass
                        else:
                            merged_result["table_summary"]["required_quantities"][item_name] = qty
        
        # 5. order_pattern_analysis 병합
        if "order_pattern_analysis" in result and isinstance(result["order_pattern_analysis"], dict):
            # 시간대별 주문 수 병합
            if "hourly_orders" in result["order_pattern_analysis"] and isinstance(result["order_pattern_analysis"]["hourly_orders"], list):
                for hourly_order in result["order_pattern_analysis"]["hourly_orders"]:
                    hour = hourly_order.get("hour", "")
                    if not hour:
                        continue
                    
                    count = hourly_order.get("count", "0")
                    if hour in merged_result["order_pattern_analysis"]["hourly_orders"]:
                        try:
                            existing_count = int(merged_result["order_pattern_analysis"]["hourly_orders"][hour])
                            new_count = int(count)
                            merged_result["order_pattern_analysis"]["hourly_orders"][hour] = existing_count + new_count
                        except (ValueError, TypeError):
                            # 변환 실패 시 그대로 유지
                            pass
                    else:
                        try:
                            merged_result["order_pattern_analysis"]["hourly_orders"][hour] = int(count)
                        except (ValueError, TypeError):
                            merged_result["order_pattern_analysis"]["hourly_orders"][hour] = 0
            
            # 인기 상품 병합
            if "popular_items" in result["order_pattern_analysis"] and isinstance(result["order_pattern_analysis"]["popular_items"], list):
                for popular_item in result["order_pattern_analysis"]["popular_items"]:
                    item_name = popular_item.get("item", "")
                    if not item_name:
                        continue
                    
                    # 주문 수량 및 건수 가져오기
                    total_quantity = popular_item.get("total_quantity", "0")
                    order_count = popular_item.get("order_count", "0")
                    
                    # 기존 항목에 추가
                    if item_name in merged_result["order_pattern_analysis"]["popular_items"]:
                        try:
                            # 수량 합산
                            existing_qty = int(merged_result["order_pattern_analysis"]["popular_items"][item_name]["total_quantity"])
                            new_qty = int(total_quantity)
                            merged_result["order_pattern_analysis"]["popular_items"][item_name]["total_quantity"] = existing_qty + new_qty
                            
                            # 주문 건수 합산
                            existing_count = int(merged_result["order_pattern_analysis"]["popular_items"][item_name]["order_count"])
                            new_count = int(order_count)
                            merged_result["order_pattern_analysis"]["popular_items"][item_name]["order_count"] = existing_count + new_count
                        except (ValueError, TypeError, KeyError):
                            # 변환 실패 시 그대로 유지
                            pass
                    else:
                        merged_result["order_pattern_analysis"]["popular_items"][item_name] = {
                            "item": item_name,
                            "total_quantity": total_quantity,
                            "order_count": order_count
                        }
            
            # 품절 상품 병합
            if "sold_out_items" in result["order_pattern_analysis"] and isinstance(result["order_pattern_analysis"]["sold_out_items"], list):
                for sold_out_item in result["order_pattern_analysis"]["sold_out_items"]:
                    if isinstance(sold_out_item, dict) and "item" in sold_out_item:
                        merged_result["order_pattern_analysis"]["sold_out_items"].add(sold_out_item["item"])
    
    # 결과를 리스트나 딕셔너리로 변환하여 반환
    print(f"결과 병합 완료: 유효 청크 {valid_results_count}개, 오류 청크 {error_results_count}개")
    
    # 0. 판매 물품 정의를 리스트로 변환
    # 마감된 상품 정보 병합
    for product_name, product in available_products_map.items():
        # sold_out_items에 있는 상품이면 deadline 정보 추가
        if product_name in merged_result["order_pattern_analysis"]["sold_out_items"]:
            if not product.get("deadline"):
                product["deadline"] = "마감됨"
    
    merged_result["available_products"] = list(available_products_map.values())
    
    # 1. item_based_summary를 리스트로 변환
    merged_result["item_based_summary"] = list(merged_result["item_based_summary"].values())
    
    # 2. 고객별 주문 목록 중복 제거
    customer_orders_dict = {}
    for order in merged_result["customer_based_orders"]:
        key = f"{order.get('customer', '')}-{order.get('item', '')}"
        if key not in customer_orders_dict:
            customer_orders_dict[key] = order
        else:
            # 이미 존재하는 주문이면 수량 합산
            try:
                existing_qty = int(customer_orders_dict[key].get("quantity", "0") or "0")
                new_qty = int(order.get("quantity", "0") or "0")
                customer_orders_dict[key]["quantity"] = str(existing_qty + new_qty)
            except (ValueError, TypeError):
                # 숫자 변환 실패 시 그대로 유지
                pass
    
    merged_result["customer_based_orders"] = list(customer_orders_dict.values())
    
    # 3. 테이블 요약 변환
    # 헤더를 리스트로 변환
    merged_result["table_summary"]["headers"] = sorted(list(merged_result["table_summary"]["headers"]))
    
    # 행을 리스트로 변환
    rows_list = []
    for customer, items_dict in merged_result["table_summary"]["rows"].items():
        row = {"customer": customer, "items": []}
        
        # 모든 헤더를 순회하면서 값 채우기
        for header in merged_result["table_summary"]["headers"]:
            row["items"].append(items_dict.get(header, ""))
        
        rows_list.append(row)
    
    merged_result["table_summary"]["rows"] = rows_list
    
    # 필요 수량을 리스트로 변환
    required_quantities = []
    for header in merged_result["table_summary"]["headers"]:
        required_quantities.append(merged_result["table_summary"]["required_quantities"].get(header, ""))
    
    merged_result["table_summary"]["required_quantities"] = required_quantities
    
    # 4. 주문 패턴 분석 변환
    # 시간대별 주문 수를 리스트로 변환
    hourly_orders_list = []
    for hour, count in merged_result["order_pattern_analysis"]["hourly_orders"].items():
        hourly_orders_list.append({"hour": hour, "count": str(count)})
    
    # 시간대 순으로 정렬
    hourly_orders_list.sort(key=lambda x: x["hour"])
    merged_result["order_pattern_analysis"]["hourly_orders"] = hourly_orders_list
    
    # 인기 상품을 리스트로 변환
    popular_items_list = list(merged_result["order_pattern_analysis"]["popular_items"].values())
    
    # 인기 순으로 정렬
    try:
        popular_items_list.sort(key=lambda x: int(x["total_quantity"]), reverse=True)
    except (ValueError, TypeError, KeyError):
        # 정렬 실패 시 그대로 유지
        pass
    
    merged_result["order_pattern_analysis"]["popular_items"] = popular_items_list
    
    # 품절 상품을 리스트로 변환
    sold_out_items_list = []
    for item in merged_result["order_pattern_analysis"]["sold_out_items"]:
        sold_out_items_list.append({"item": item, "sold_out_time": ""})
    
    merged_result["order_pattern_analysis"]["sold_out_items"] = sold_out_items_list
    
    # 최종 로깅
    print(f"최종 병합 결과: 판매 물품 {len(merged_result['available_products'])}개, "
          f"주문자별 주문 {len(merged_result['customer_based_orders'])}개, "
          f"품목별 요약 {len(merged_result['item_based_summary'])}개")
    
    return merged_result

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
    
    # 판매자 메시지에서 판매 상품 정보 추출 (전체 대화 기준)
    try:
        product_info = extract_product_info_from_seller_messages(conversation_text)
        available_products = get_available_products(conversation_text)
        print(f"전체 대화에서 추출한 판매 상품 정보: {len(available_products)}개 상품")
        
        # 상품 정보 정리 (로깅 목적)
        for category, products in product_info.items():
            if products:
                product_names = [p['name'] for p in products]
                print(f"  - {category} 카테고리: {', '.join(product_names[:3])}{'...' if len(product_names) > 3 else ''}")
    except Exception as e:
        print(f"상품 정보 추출 중 오류 발생: {str(e)}")
        product_info = {}
        available_products = set()
    
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
        
        # 각 청크별로 병렬 분석 수행 (ThreadPoolExecutor 사용)
        # 최대 동시 처리 스레드 수를 제한하여 API 제한에 걸리지 않도록 함
        max_workers = min(5, len(chunks))  # 최대 5개 스레드 또는 청크 수만큼 (더 적은 쪽으로)
        results = []
        
        print(f"병렬 처리 시작: {max_workers} 개의 스레드로 {len(chunks)} 개의 청크 처리")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 각 청크에 대한 future 생성
            future_to_chunk = {
                executor.submit(analyze_conversation_chunk, chunk, start_date, end_date, shop_name): i 
                for i, chunk in enumerate(chunks)
            }
            
            # future가 완료됨에 따라 결과 수집
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    chunk_result = future.result()
                    print(f"청크 {chunk_index+1}/{len(chunks)} 분석 완료")
                    
                    # 유효한 데이터가 있는지 로깅
                    has_data = False
                    customer_count = 0
                    
                    if "customer_based_orders" in chunk_result and isinstance(chunk_result["customer_based_orders"], list):
                        customer_count = len(chunk_result["customer_based_orders"])
                        has_data = customer_count > 0
                        
                    print(f"청크 {chunk_index+1} 결과: 주문자별 주문 내역 {customer_count}개")
                    
            results.append(chunk_result)
                except Exception as exc:
                    print(f"청크 {chunk_index+1} 처리 중 오류 발생: {exc}")
                    # 에러가 발생해도 빈 결과 구조를 추가하여 인덱스 유지
                    results.append({
                        "time_based_orders": [],
                        "item_based_summary": [],
                        "customer_based_orders": [],
                        "table_summary": {
                            "headers": [],
                            "rows": [],
                            "required_quantities": []
                        },
                        "order_pattern_analysis": {
                            "hourly_orders": [],
                            "popular_items": [],
                            "sold_out_items": []
                        },
                        "error": f"Chunk processing error: {str(exc)}",
                        "message": f"청크 {chunk_index+1} 처리 중 오류가 발생했습니다."
                    })
        
        # 분석 결과 병합
        print(f"모든 청크 처리 완료, 결과 병합 시작")
        merged_result = merge_analysis_results(results)
        
        # 판매 상품 정보를 활용하여 최종 필터링
        if available_products:
            print(f"판매 상품 정보를 활용하여 최종 필터링 시작 (활용 가능한 상품: {len(available_products)}개)")
            
            # 고객 주문 목록 필터링
            if "customer_based_orders" in merged_result and merged_result["customer_based_orders"]:
                original_count = len(merged_result["customer_based_orders"])
                merged_result["customer_based_orders"] = [
                    order for order in merged_result["customer_based_orders"]
                    if is_valid_item_name(order.get("item", ""), available_products)
                ]
                filtered_count = original_count - len(merged_result["customer_based_orders"])
                if filtered_count > 0:
                    print(f"최종 필터링: customer_based_orders에서 {filtered_count}개의 잘못된 품목이 제외되었습니다.")
            
            # 품목별 요약 필터링
            if "item_based_summary" in merged_result and merged_result["item_based_summary"]:
                original_count = len(merged_result["item_based_summary"])
                merged_result["item_based_summary"] = [
                    item for item in merged_result["item_based_summary"]
                    if is_valid_item_name(item.get("item", ""), available_products)
                ]
                filtered_count = original_count - len(merged_result["item_based_summary"])
                if filtered_count > 0:
                    print(f"최종 필터링: item_based_summary에서 {filtered_count}개의 잘못된 품목이 제외되었습니다.")
        
        return merged_result
    else:
        # 단일 청크 분석
        result = analyze_conversation_chunk(filtered_conversation, start_date, end_date, shop_name)
        
        # 판매 상품 정보를 활용하여 최종 필터링 (단일 청크인 경우에도)
        if available_products:
            print(f"판매 상품 정보를 활용하여 최종 필터링 시작 (활용 가능한 상품: {len(available_products)}개)")
            
            # 고객 주문 목록 필터링
            if "customer_based_orders" in result and result["customer_based_orders"]:
                original_count = len(result["customer_based_orders"])
                result["customer_based_orders"] = [
                    order for order in result["customer_based_orders"]
                    if is_valid_item_name(order.get("item", ""), available_products)
                ]
                filtered_count = original_count - len(result["customer_based_orders"])
                if filtered_count > 0:
                    print(f"최종 필터링: customer_based_orders에서 {filtered_count}개의 잘못된 품목이 제외되었습니다.")
            
            # 품목별 요약 필터링
            if "item_based_summary" in result and result["item_based_summary"]:
                original_count = len(result["item_based_summary"])
                result["item_based_summary"] = [
                    item for item in result["item_based_summary"]
                    if is_valid_item_name(item.get("item", ""), available_products)
                ]
                filtered_count = original_count - len(result["item_based_summary"])
                if filtered_count > 0:
                    print(f"최종 필터링: item_based_summary에서 {filtered_count}개의 잘못된 품목이 제외되었습니다.")
        
        return result

def analyze_conversation_chunk(conversation_text, start_date=None, end_date=None, shop_name=None):
    """
    단일 대화 청크를 분석합니다.
    
    Args:
        conversation_text (str): 분석할 대화 청크
        start_date, end_date, shop_name: 원래 함수와 동일
        
    Returns:
        dict: 분석 결과
    """
    system_prompt = """
 당신은 카카오톡 대화 내역을 분석하여 주문 정보를 정확하게 추출하는 전문가입니다. 다음 지침에 따라 철저하게 분석해주세요:

## 판매자 식별
1. 다음 패턴의 사용자명은 판매자로 간주하고 그들의 메시지는 주문으로 처리하지 마세요:
   - "우국상", "신검단", "국민상회", "머슴", "오픈채팅봇", "삐" 등의 키워드가 포함된 사용자명
2. 판매자 메시지 중 공지사항, 상품 소개, 마감 안내 등은 별도로 식별하여 참조 정보로 활용하세요.

## 판매 물품 식별
1. 판매자 사용자명의 주요 키워드인 ["우국상", "신검단", "국민상회", "머슴", "오픈채팅봇"] 의 메시지에서 '판매물품/품목'을 판단하세요.
2. '판매물품/품목'을 판단한 후에 해당 '판매물품/품목'을 기준으로 주문 데이터를 추출합니다.

## 대화 분석 규칙
1. 대화에서 날짜 정보는 '2025년 4월 26일'과 같은 형식으로 표시됩니다. 해당 날짜를 기준으로 대화를 분리하세요.
2. 주문 형식은 다음 패턴을 모두 인식합니다:
   - "[닉네임] / [전화번호 뒷자리] / [상품명+수량]" (표준 형식)
   - "[닉네임] [전화번호 뒷자리] [상품명+수량]" (구분자 없음)
   - "[전화번호 뒷자리] / [상품명+수량]" (닉네임 생략)
   - "[닉네임] / [상품명+수량]" (전화번호 생략)
3. 주문자는 다음 형식으로 식별합니다:
   - 일반 닉네임: "해피쏭", "민쓰" 등
   - 이모티콘 포함: "👍", "♡카르페디엠♡" 등
   - 캐릭터 관련: "라이언님", "프로도" 등
   - 가족관계 표현: "두식맘♡", "삼남매맘" 등
   - 번호 포함: "크림 2821", "4212동라이언" 등
4. 주문 수정/취소는 다음 패턴으로 인식합니다:
   - "[닉네임/번호] [상품명] [수량] 취소" (취소)
   - "[닉네임/번호] [상품명] [수량]로 변경" (변경)
   - "[닉네임/번호] [상품명] [수량] 추가" (추가)
5. 마감 안내는 "❌마감❌", "마감되었습니다" 등의 표현을 포함한 판매자 메시지로 식별합니다.

## 정보 추출 방법
1. 주문 메시지에서는 다음 정보를 추출하세요:
   - 시간: 메시지 발송 시간
   - 주문자: 닉네임과 전화번호 뒷자리 (가능한 경우)
   - 품목: 주문한 상품명 (상품명 표준화 필요)
   - 수량: 주문 수량 (기본값은 1개)
   - 비고: 특이사항 (픽업일, 취소여부, 변경사항 등)

2. 주문 메시지에 여러 품목이 포함된 경우 각 품목별로 분리하여 기록하세요.
   예: "하트뿅 3007 나주곰탕3팩, 불고기 1세트, 고구마케이크 1개" → 세 개의 주문으로 분리

3. 주문 취소나 변경 시 기존 주문을 찾아 상태를 업데이트하세요.

4. 상품 카테고리 및 수령일 정보:
   - 공동구매 상품: 주문 시점과 수령일이 다름(월요일, 수요일, 금요일 등 명시)
   - 현장판매 상품: 당일 수령 가능한 상품

## 결과 출력 형식
분석 결과는 다음 여섯 가지 형태로 정리하세요:

1. 판매물품 정의: 판매자가 언급한 모든 판매 물품 목록
   - 물품명, 가격, 카테고리, 수령일(있는 경우), 마감 정보(있는 경우)
   - 이 정보는 이후 주문 분석에 활용

2. 시간순 주문 내역: 주문이 들어온 시간 순서로 정렬
   - 시간, 주문자, 품목, 수량, 수령일, 비고 포함

3. 품목별 총 주문 갯수:
   - 품목명, 총 수량, 해당 품목을 주문한 주문자 목록(수량 포함) 표시
   - 품목의 카테고리와 수령일 포함

4. 주문자별 주문 내역:
   - 주문자, 품목, 수량, 수령일, 비고 포함
   - 주문자가 여러 품목을 주문한 경우 각각 별도 행으로 표시
   - 비고는 해당 주문자의 첫 번째 항목에만 표시

5. 주문자-상품 교차표:
   - 행: 주문자(닉네임+전화번호)
   - 열: 상품명
   - 각 셀: 해당 주문자가 주문한 해당 상품의 수량
   - 마지막 행에는 각 상품별 총 필요 수량 표시
   - 주문자가 상품을 주문하지 않은 경우 빈칸으로 표시

6. 주문 패턴 분석:
   - 시간대별 주문 건수
   - 인기 상품 순위
   - 마감된 상품 목록과 마감 시간
    """
    
    # 판매자 메시지에서 판매 상품 정보 추출
    try:
        product_info = extract_product_info_from_seller_messages(conversation_text)
        available_products = get_available_products(conversation_text)
        print(f"판매자 메시지에서 추출한 상품 정보: {len(available_products)}개 상품")
        
        # 상품 정보 정리 (로깅 목적)
        for category, products in product_info.items():
            if products:
                product_names = [p['name'] for p in products]
                print(f"  - {category}: {', '.join(product_names)}")
    except Exception as e:
        print(f"상품 정보 추출 중 오류 발생: {str(e)}")
        product_info = {}
        available_products = set()
    
    # Create the user prompt with instructions
    date_guidance = ""
    if start_date and end_date:
        date_guidance = f"\n기간 제한: {start_date}부터 {end_date}까지의 대화만 분석해주세요."
    elif start_date:
        date_guidance = f"\n기간 제한: {start_date}부터의 대화만 분석해주세요."
    elif end_date:
        date_guidance = f"\n기간 제한: {end_date}까지의 대화만 분석해주세요."
        
    shop_context = f"\n이 대화는 '{shop_name}' 상점의 주문 내역입니다." if shop_name else ""
    
    # 상품 정보를 프롬프트에 추가
    product_context = "\n\n## 판매 상품 정보:\n"
    for category, products in product_info.items():
        if products:
            product_context += f"\n### {category}:\n"
            for product in products:
                product_context += f"- {product['name']}"
                if product.get('price'):
                    product_context += f" ({product['price']}원)"
                if product.get('deadline'):
                    product_context += f" - {product['deadline']}"
                if product.get('delivery_date'):
                    product_context += f" - 수령일: {product['delivery_date']}"
                product_context += "\n"
    
    # JSON 포맷 템플릿을 별도 변수로 분리
    json_template = '''
    ```json
    {
      "available_products": [
        {
          "name": "상품명",
          "price": "가격",
          "category": "카테고리",
          "delivery_date": "수령일",
          "deadline": "마감정보"
        }
      ],
      "time_based_orders": [
        {
          "time": "시간",
          "customer": "주문자",
          "item": "품목",
          "quantity": "수량",
          "delivery_date": "수령일",
          "note": "비고"
        }
      ],
      "item_based_summary": [
        {
          "item": "품목명",
          "category": "카테고리",
          "total_quantity": "총 수량",
          "delivery_date": "수령일",
          "customers": "주문자 목록"
        }
      ],
      "customer_based_orders": [
        {
          "customer": "주문자명",
          "item": "품목명",
          "quantity": "수량",
          "delivery_date": "수령일",
          "note": "비고"
        }
      ],
      "table_summary": {
        "headers": ["상품명1", "상품명2", "..."],
        "rows": [
          {
            "customer": "주문자명1",
            "items": ["수량1", "수량2", "..."]
          },
          "..."
        ],
        "required_quantities": ["총수량1", "총수량2", "..."]
      },
      "order_pattern_analysis": {
        "hourly_orders": [
          {
            "hour": "시간대",
            "count": "주문건수"
          }
        ],
        "popular_items": [
          {
            "item": "상품명",
            "total_quantity": "총 수량",
            "order_count": "주문건수"
          }
        ],
        "sold_out_items": [
          {
            "item": "상품명",
            "sold_out_time": "마감시간"
          }
        ]
      }
    }
    ```
    '''
    
    # 템플릿과 변수를 조합하여 최종 프롬프트 생성
    user_prompt = f"""
    아래 KakaoTalk 대화 내역을 분석하여 주문 정보를 추출해주세요.{date_guidance}{shop_context}
    
    이 대화는 카카오톡 공동구매 단체방의 대화 내역입니다. 다음과 같은 사항에 주의하여 분석해주세요:

    1. 먼저 판매자 메시지를 분석하여 판매물품/품목을 파악하고, 이를 available_products 필드에 정리해주세요.
    2. 주문 메시지는 "[닉네임]/[전화번호 뒷자리]/[상품명+수량]" 형식이지만, 다양한 변형이 있을 수 있습니다.
    3. 판매자("우국상 신검단", "국민상회 머슴" 등)의 메시지는 주문이 아닌 공지사항으로 처리하세요.
    4. 동일 상품에 대한 주문 취소나 변경 내역이 있을 수 있으므로 이를 반영해주세요.
    5. 상품별로 수령일이 다른 경우가 있으니 판매자의 공지를 참조하여 수령일을 추출해주세요.
    {product_context}
    
    분석 결과는 다음 6가지 테이블로 구성해주세요:
    
    1. 판매물품 정의: 대화에서 판매자가 언급한 모든 판매 물품 목록
       - 물품명, 가격, 카테고리, 수령일(있는 경우), 마감 정보(있는 경우)
       - 이 정보는 이후 주문 분석에 활용
       
    2. 시간순 주문 내역: 대화에서 언급된 모든 주문을 시간 순서대로 정리
       - 시간, 주문자, 품목, 수량, 수령일, 비고 포함
           
    3. 품목별 총 주문 갯수: 각 품목별 총 주문량 정리
       - 품목명, 총 수량, 수령일, 주문자 목록 포함
           
    4. 주문자별 주문 내역: 주문자 기준으로 주문 내용 정리
       - 주문자, 품목, 수량, 수령일, 비고 포함
           
    5. 주문자-상품 교차표: 주문자와 상품을 축으로 하는 테이블
       - 행: 주문자, 열: 상품명
       - 각 셀: 해당 주문자가 주문한 해당 상품의 수량
       - 마지막 행에는 총 필요수량 표시
    
    6. 주문 패턴 분석: 추가적인 인사이트 제공
       - 시간대별 주문 건수
       - 인기 상품 순위
       - 마감된 상품 목록
           
    반드시 JSON 형식으로 응답해주세요. 응답 형식은 다음과 같습니다:
    {json_template}
    
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
            
            # 응답에서 텍스트 콘텐츠 찾기
            content = None
            
            # 응답 구조 확인
            if hasattr(response, 'content') and response.content:
            # content가 문자열인 경우를 처리
            if isinstance(response.content, str):
                content = response.content
                print("Content is a string, length:", len(content))
                # 콘텐츠가 리스트인 경우 (일반적인 경우)
            elif isinstance(response.content, list):
                # ThinkingBlock과 TextBlock 객체를 모두 처리
                all_blocks_text = []
                has_json = False
                
                    for item in response.content:
                    item_text = None
                    
                        if hasattr(item, 'text') and item.text:
                        item_text = item.text
                        # JSON 블록을 찾음
                        if '```json' in item_text or item_text.strip().startswith('{') and item_text.strip().endswith('}'):
                            has_json = True
                    elif hasattr(item, 'thinking') and item.thinking:
                        # ThinkingBlock에서도 JSON 형식의 텍스트를 찾음
                        thinking_text = item.thinking
                        if '```json' in thinking_text:
                            # JSON 블록 추출 시도
                            json_match = re.search(r'```json\s*(.*?)\s*```', thinking_text, re.DOTALL)
                            if json_match:
                                item_text = f"```json\n{json_match.group(1)}\n```"
                                has_json = True
                    elif hasattr(item, 'value') and item.value:
                        item_text = item.value
                        elif isinstance(item, str):
                        item_text = item
                        else:
                            print(f"Content item type: {type(item)}")
                        try:
                            # 다양한 방법으로 텍스트 추출 시도
                            if hasattr(item, '__str__'):
                                item_text = item.__str__()
                            elif hasattr(item, '__repr__'):
                                item_text = item.__repr__()
                            else:
                                item_text = str(item)
                            except:
                            print(f"Failed to extract text from item of type {type(item)}")
                    
                    if item_text:
                        all_blocks_text.append(item_text)
                
                # JSON 블록이 있는 텍스트 우선, 없으면 모든 텍스트 연결
                if has_json:
                    for text in all_blocks_text:
                        if '```json' in text or (text.strip().startswith('{') and text.strip().endswith('}')):
                            content = text
                            break
                
                # JSON 블록이 없거나 찾지 못한 경우 모든 텍스트 연결
                if not content:
                    content = "\n".join(all_blocks_text)
            
            # content가 다른 타입인 경우 (dict 등)
            else:
                    content = str(response.content)
            
            # 콘텐츠를 찾지 못한 경우 전체 응답을 문자열로 변환
            if content is None:
            print("Content extraction failed, using full response...")
                # 모든 응답의 문자열 표현 시도
                if hasattr(response, 'model_dump_json'):
                    content = response.model_dump_json()  # Pydantic 모델인 경우
                else:
                    content = str(response)
            
        print(f"Extracted content length: {len(content)} characters")
        print(f"Extracted content start: {content[:100]}...")  # 처음 100자만 로깅
            
            # 콘텐츠가 정상적으로 추출되었는지 확인
        if not content or len(content.strip()) == 0:
            print("⚠️ 경고: API 응답 콘텐츠가 비어 있습니다! 대화에서 직접 주문 추출 시도.")
            # 대화에서 직접 주문 데이터 추출 시도
            # 기본 패턴: 시간, 주문자, 주문 내용 추출
            orders = extract_orders_directly(conversation_text)
            if orders:
                print(f"대화에서 직접 {len(orders)}개 주문을 추출했습니다.")
                result = {
                    "time_based_orders": orders,
                    "item_based_summary": summarize_items(orders),
                    "customer_based_orders": orders.copy(),  # time_based_orders와 동일하게 설정
                    "table_summary": {
                        "headers": [],
                        "rows": [],
                        "required_quantities": []
                    },
                    "order_pattern_analysis": {
                        "hourly_orders": [],
                        "popular_items": [],
                        "sold_out_items": []
                    }
                }
                return result
            else:
                return {
                    "error": "Empty API response",
                    "message": "API 응답이 비어있고 대화에서 직접 주문을 추출할 수 없습니다.",
                    "time_based_orders": [],
                    "item_based_summary": [],
                    "customer_based_orders": [],
                    "table_summary": {"headers": [], "rows": [], "required_quantities": []},
                    "order_pattern_analysis": {
                        "hourly_orders": [],
                        "popular_items": [],
                        "sold_out_items": []
                    }
                }
            
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

                # customer_based_orders가 없거나 비어 있으면 time_based_orders로부터 생성
                if (
                    ("customer_based_orders" not in result or not result["customer_based_orders"])
                    and "time_based_orders" in result
                    and isinstance(result["time_based_orders"], list)
                    and len(result["time_based_orders"]) > 0
                ):
                    print("customer_based_orders가 비어 있어 time_based_orders로부터 생성합니다.")
                    result["customer_based_orders"] = [
                        {
                            "customer": o.get("customer", ""),
                            "item": o.get("item", ""),
                            "quantity": o.get("quantity", ""),
                            "delivery_date": o.get("delivery_date", ""),
                            "note": o.get("note", "")
                        }
                        for o in result["time_based_orders"]
                    ]
                    print(f"생성된 customer_based_orders: {len(result['customer_based_orders'])}개")

                # 필수 필드 확인 및 생성
                for required_key in ["time_based_orders", "item_based_summary", "customer_based_orders", "table_summary", "order_pattern_analysis"]:
                    if required_key not in result:
                        if required_key == "time_based_orders":
                            # time_based_orders가 없는 경우
                            # Regex를 사용해 시간, 주문자, 상품, 수량 패턴을 찾아서 직접 추출
                            print(f"⚠️ 경고: {required_key} 필드가 응답에 없습니다! 대화에서 직접 추출을 시도합니다.")
                            orders = extract_orders_from_content(content) or extract_orders_directly(conversation_text)
                            if orders:
                                result[required_key] = orders
                                print(f"직접 추출에 성공했습니다: {len(orders)}개 주문.")
                            else:
                                result[required_key] = []
                        elif required_key == "customer_based_orders" and "time_based_orders" in result:
                            # time_based_orders가 있으면 복사해서 사용
                            print(f"⚠️ 경고: {required_key} 필드가 응답에 없습니다! time_based_orders에서 복사합니다.")
                            result[required_key] = result["time_based_orders"].copy()
                        elif required_key == "item_based_summary" and "time_based_orders" in result:
                            # time_based_orders가 있으면 요약 생성
                            print(f"⚠️ 경고: {required_key} 필드가 응답에 없습니다! time_based_orders에서 생성합니다.")
                            result[required_key] = summarize_items(result["time_based_orders"])
                        elif required_key == "table_summary":
                            # 비어있는 테이블 요약 구조 생성
                            result[required_key] = {"headers": [], "rows": [], "required_quantities": []}
                        elif required_key == "order_pattern_analysis":
                            # 비어있는 주문 패턴 분석 구조 생성
                            result[required_key] = {
                                "hourly_orders": [],
                                "popular_items": [],
                                "sold_out_items": []
                            }
                
                # 품목 필터링 로직 적용 - 추출한 판매 상품 목록 활용
                # 1. time_based_orders 필터링
                if "time_based_orders" in result and result["time_based_orders"]:
                    original_count = len(result["time_based_orders"])
                    result["time_based_orders"] = [
                        order for order in result["time_based_orders"]
                        if is_valid_item_name(order.get("item", ""), available_products)
                    ]
                    filtered_count = original_count - len(result["time_based_orders"])
                    if filtered_count > 0:
                        print(f"time_based_orders에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                
                # 2. item_based_summary 필터링
                if "item_based_summary" in result and result["item_based_summary"]:
                    original_count = len(result["item_based_summary"])
                    result["item_based_summary"] = [
                        item for item in result["item_based_summary"]
                        if is_valid_item_name(item.get("item", ""), available_products)
                    ]
                    filtered_count = original_count - len(result["item_based_summary"])
                    if filtered_count > 0:
                        print(f"item_based_summary에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                
                # 3. customer_based_orders 필터링
                if "customer_based_orders" in result and result["customer_based_orders"]:
                    original_count = len(result["customer_based_orders"])
                    result["customer_based_orders"] = [
                        order for order in result["customer_based_orders"]
                        if is_valid_item_name(order.get("item", ""), available_products)
                    ]
                    filtered_count = original_count - len(result["customer_based_orders"])
                    if filtered_count > 0:
                        print(f"customer_based_orders에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                
                # 교차표 헤더 필터링
                if "table_summary" in result and "headers" in result["table_summary"]:
                    original_count = len(result["table_summary"]["headers"])
                    result["table_summary"]["headers"] = [
                        header for header in result["table_summary"]["headers"]
                        if is_valid_item_name(header, available_products)
                    ]
                    filtered_count = original_count - len(result["table_summary"]["headers"])
                    if filtered_count > 0:
                        print(f"table_summary 헤더에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                    
                    # 헤더가 필터링되었다면 rows와 required_quantities도 조정
                    if filtered_count > 0 and "rows" in result["table_summary"]:
                        # rows 조정은 더 복잡하므로 여기서는 생략하고 merge_analysis_results에서 처리
                        print("헤더 필터링으로 인해 교차표 구조를 merge_analysis_results에서 재구성합니다.")
                
                # 4. order_pattern_analysis의 popular_items 필터링
                if "order_pattern_analysis" in result and "popular_items" in result["order_pattern_analysis"]:
                    original_count = len(result["order_pattern_analysis"]["popular_items"])
                    result["order_pattern_analysis"]["popular_items"] = [
                        item for item in result["order_pattern_analysis"]["popular_items"]
                        if is_valid_item_name(item.get("item", ""), available_products)
                    ]
                    filtered_count = original_count - len(result["order_pattern_analysis"]["popular_items"])
                    if filtered_count > 0:
                        print(f"popular_items에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                
                # 5. order_pattern_analysis의 sold_out_items 필터링
                if "order_pattern_analysis" in result and "sold_out_items" in result["order_pattern_analysis"]:
                    original_count = len(result["order_pattern_analysis"]["sold_out_items"])
                    result["order_pattern_analysis"]["sold_out_items"] = [
                        item for item in result["order_pattern_analysis"]["sold_out_items"]
                        if is_valid_item_name(item.get("item", ""), available_products)
                    ]
                    filtered_count = original_count - len(result["order_pattern_analysis"]["sold_out_items"])
                    if filtered_count > 0:
                        print(f"sold_out_items에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")
                
                # 빈 배열 확인
                for key in ["time_based_orders", "item_based_summary", "customer_based_orders"]:
                    if key in result and (not isinstance(result[key], list) or len(result[key]) == 0):
                        if key == "time_based_orders":
                            # time_based_orders가 비어있는 경우
                            orders = extract_orders_from_content(content) or extract_orders_directly(conversation_text)
                            if orders:
                                result[key] = orders
                                print(f"⚠️ 경고: {key} 배열이 비어 있습니다! 대화에서 직접 {len(orders)}개 추출했습니다.")
                            
                            # customer_based_orders도 업데이트
                            if orders and ("customer_based_orders" not in result or len(result["customer_based_orders"]) == 0):
                                result["customer_based_orders"] = orders.copy()
                                print(f"customer_based_orders도 함께 업데이트했습니다.")
                            
                            # item_based_summary도 업데이트
                            if orders and ("item_based_summary" not in result or len(result["item_based_summary"]) == 0):
                                result["item_based_summary"] = summarize_items(orders)
                                print(f"item_based_summary도 함께 업데이트했습니다.")
                
                # customer_based_orders 개수 로깅
                if "customer_based_orders" in result and isinstance(result["customer_based_orders"], list):
                    print(f"JSON contains {len(result['customer_based_orders'])} customer_based_orders")
                
                # 추가 로깅 - 다른 필드도 로깅
                if "time_based_orders" in result and isinstance(result["time_based_orders"], list):
                    print(f"JSON contains {len(result['time_based_orders'])} time_based_orders")
                
                if "item_based_summary" in result and isinstance(result["item_based_summary"], list):
                    print(f"JSON contains {len(result['item_based_summary'])} item_based_summary")
                
                # 결과가 완전히 빈 경우 (모든 키의 배열이 비어있는 경우)
                if (
                    (not result.get("time_based_orders")) and
                    (not result.get("item_based_summary")) and
                    (not result.get("customer_based_orders"))
                ):
                    print("⚠️ 경고: 모든 결과 배열이 비어 있습니다! 최후의 추출 시도...")
                    orders = extract_orders_directly(conversation_text)
                    if orders:
                        result["time_based_orders"] = orders
                        result["customer_based_orders"] = orders.copy()
                        result["item_based_summary"] = summarize_items(orders)
                        print(f"최후 추출 성공: {len(orders)}개 주문.")
                
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
                    
                # 정규표현식을 통한 주문 추출 시도
                print("JSON 파싱 실패, 대화에서 직접 주문 데이터 추출 시도...")
                orders = extract_orders_from_content(content) or extract_orders_directly(conversation_text)
                
                if orders:
                    print(f"대화에서 직접 {len(orders)}개 주문을 추출했습니다.")
                    result = {
                        "time_based_orders": orders,
                        "item_based_summary": summarize_items(orders),
                        "customer_based_orders": orders.copy(),
                        "table_summary": {
                            "headers": [],
                            "rows": [],
                            "required_quantities": []
                        },
                        "order_pattern_analysis": {
                            "hourly_orders": [],
                            "popular_items": [],
                            "sold_out_items": []
                        }
                    }
                            return result
                
                # 빈 결과 구조 생성 - 하지만 완전히 비우지 않고 최소한의 구조는 유지
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
                    "order_pattern_analysis": {
                        "hourly_orders": [],
                        "popular_items": [],
                        "sold_out_items": []
                    },
                    "error": "JSON parsing failed",
                    "message": str(parse_error)
                }
        except Exception as extract_error:
            print(f"Response content extraction and parsing failed: {str(extract_error)}")
            # 예외 발생 시 스택 트레이스 로깅
            import traceback
            traceback.print_exc()
            
            # 마지막 수단으로 대화에서 직접 주문 데이터 추출 시도
            print("구문 분석 실패, 대화에서 직접 주문 데이터 추출 시도...")
            orders = extract_orders_from_content(content) or extract_orders_directly(conversation_text)
            
            if orders:
                print(f"대화에서 직접 {len(orders)}개 주문을 추출했습니다.")
                result = {
                    "time_based_orders": orders,
                    "item_based_summary": summarize_items(orders),
                    "customer_based_orders": orders.copy(),
                    "table_summary": {
                        "headers": [],
                        "rows": [],
                        "required_quantities": []
                    },
                    "order_pattern_analysis": {
                        "hourly_orders": [],
                        "popular_items": [],
                        "sold_out_items": []
                    }
                }
                return result
            
                return {
                "error": "Response content extraction failed", 
                "message": str(extract_error), 
                "response_info": str(response)[:500],
                    "time_based_orders": [],
                    "item_based_summary": [],
                    "customer_based_orders": [],
                    "table_summary": {
                        "headers": [],
                        "rows": [],
                        "required_quantities": []
                    },
                "order_pattern_analysis": {
                    "hourly_orders": [],
                    "popular_items": [],
                    "sold_out_items": []
                }
            }
    except Exception as e:
        # 자세한 예외 정보와 추적을 위한 로깅
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error occurred: {str(e)}")
        print(f"Traceback: {error_trace}")
        
        # 마지막 수단으로 대화에서 직접 주문 데이터 추출 시도
        print("API 호출 실패, 대화에서 직접 주문 데이터 추출 시도...")
        orders = extract_orders_from_content(conversation_text) or extract_orders_directly(conversation_text)
        
        if orders:
            print(f"대화에서 직접 {len(orders)}개 주문을 추출했습니다.")
            result = {
                "time_based_orders": orders,
                "item_based_summary": summarize_items(orders),
                "customer_based_orders": orders.copy(),
                "table_summary": {
                    "headers": [],
                    "rows": [],
                    "required_quantities": []
                },
                "order_pattern_analysis": {
                    "hourly_orders": [],
                    "popular_items": [],
                    "sold_out_items": []
                }
            }
            return result
        
        # 에러 상세 정보 반환
        return {
            "error": "API call failed", 
            "message": str(e),
            "traceback": error_trace[:500] if error_trace else None,
            "time_based_orders": [],
            "item_based_summary": [],
            "customer_based_orders": [],
            "table_summary": {
                "headers": [],
                "rows": [],
                "required_quantities": []
            },
            "order_pattern_analysis": {
                "hourly_orders": [],
                "popular_items": [],
                "sold_out_items": []
            }
        }

def is_valid_item_name(item_name, available_products=None):
    """
    품목명이 유효한지 검증합니다.
    
    Args:
        item_name (str): 검증할 품목명
        available_products (set, optional): 판매자가 언급한 사용 가능한 상품 목록
        
    Returns:
        bool: 유효한 품목명이면 True, 아니면 False
    """
    if not item_name or not isinstance(item_name, str):
        return False
        
    # 너무 짧은 품목명은 제외 (2자 미만)
    if len(item_name.strip()) < 2:
        return False
    
    # 숫자로만 이루어진 품목명 제외
    if item_name.strip().isdigit():
        return False
    
    # 날짜/시간 패턴이 포함된 품목명 제외
    date_patterns = [
        r'\d{4}년',              # 년도 패턴
        r'\d{1,2}월\s*\d{1,2}일', # 월일 패턴
        r'오전|오후',              # 오전/오후 패턴
        r'\d{1,2}:\d{2}',        # 시간 패턴
        r'\d{2}\.\d{2}'          # 날짜 포맷 (01.23)
    ]
    
    for pattern in date_patterns:
        if re.search(pattern, item_name):
            return False
    
    # 주문자 정보로 보이는 패턴 제외 (전화번호가 포함된 패턴)
    if re.search(r'[가-힣a-zA-Z]+\s+\d{3,4}$', item_name):  # 예: '크림 282', '흰둥맘 379'
        return False
    
    # 특정 미니멀한 단어들 제외
    invalid_words = ['즈', '고', '린', '월', '후', '국', '탕', '사골', '수', '선', '주', '갈',
                     '주문', '확인', '냄', '햇', '삼', '개', '건', '번', '그램', '킬로']
    if item_name.strip() in invalid_words:
        return False

    # 주문자/가격 정보로 보이는 패턴 제외
    price_patterns = [
        r'^\d+원$',               # 가격 (예: "3000원")
        r'^\d+,\d+원$',           # 콤마 포함 가격 (예: "3,000원")
        r'입금',                   # 입금 관련 문구
        r'결제',                   # 결제 관련 문구
        r'가격',                   # 가격 문구
        r'^\d+$'                  # 숫자만 있는 경우
    ]
    
    for pattern in price_patterns:
        if re.search(pattern, item_name):
            return False
    
    # 판매 물품 목록에 있는지 확인 (available_products가 제공된 경우)
    if available_products and len(available_products) > 0:
        # 정확한 완전 일치
        if item_name in available_products:
            return True
        
        # 대략적인 부분 일치 검사 (품목명 정규화 고려)
        normalized_item = item_name.strip().lower()
        for product in available_products:
            normalized_product = product.strip().lower()
            
            # 완전 포함 관계
            if normalized_item in normalized_product or normalized_product in normalized_item:
                # 너무 짧은 부분 매칭은 제외 (예: "곰" -> "곰탕"은 매칭되지만 너무 짧음)
                min_length = min(len(normalized_item), len(normalized_product))
                if min_length < 2:
                    continue
                    
                return True
            
            # 특수 케이스 처리
            # 한글 자모음 분리 없이 기본적인 유사도 판단
            # 예: "소고기 국밥" vs "소고기국밥"
            product_no_space = normalized_product.replace(" ", "")
            item_no_space = normalized_item.replace(" ", "")
            
            if product_no_space == item_no_space:
                return True
            
            # 접미사/접두사 처리 (예: "한우곰탕" vs "곰탕")
            # 품목의 핵심 키워드가 포함되어 있고, 길이가 비슷한 경우
            if (product_no_space in item_no_space or item_no_space in product_no_space) and \
               abs(len(product_no_space) - len(item_no_space)) <= 3:
                return True
        
        # 어떤 판매 물품과도 매칭되지 않음 
        return False
        
    # available_products가 없는 경우 기본 필터링만 적용
    return True

def summarize_items(orders):
    """
    주문 목록에서 품목별 요약을 생성합니다.
    
    Args:
        orders (list): 주문 목록
        
    Returns:
        list: 품목별 요약 목록
    """
    item_summary = {}
    filtered_items_count = 0
    
    for order in orders:
        item = order.get("item", "")
        customer = order.get("customer", "")
        quantity = order.get("quantity", "1")
        delivery_date = order.get("delivery_date", "")
        
        # 품목명 유효성 검증
        if not item or not is_valid_item_name(item):
            filtered_items_count += 1
            continue
        
        if item not in item_summary:
            item_summary[item] = {
                "item": item,
                "category": "",
                "total_quantity": "0",
                "delivery_date": delivery_date,
                "customers": ""
            }
        
        # 수량 합산
        try:
            current_total = int(item_summary[item]["total_quantity"])
            order_quantity = int(quantity) if quantity else 1
            item_summary[item]["total_quantity"] = str(current_total + order_quantity)
        except (ValueError, TypeError):
            # 숫자로 변환할 수 없는 경우 문자열 그대로 유지
            pass
        
        # 수령일 업데이트 (비어있는 경우에만)
        if not item_summary[item]["delivery_date"] and delivery_date:
            item_summary[item]["delivery_date"] = delivery_date
        
        # 주문자 목록 업데이트
        if customer:
            customer_entry = f"{customer}({quantity or '1'})"
            current_customers = item_summary[item]["customers"]
            
            if current_customers:
                item_summary[item]["customers"] = f"{current_customers}, {customer_entry}"
            else:
                item_summary[item]["customers"] = customer_entry
    
    if filtered_items_count > 0:
        print(f"품목 필터링: {filtered_items_count}개의 잘못된 품목명이 제외되었습니다.")
    
    return list(item_summary.values())

def extract_orders_from_content(content):
    """
    Claude API 응답 콘텐츠에서 주문 정보를 직접 추출합니다.
    
    Args:
        content (str): 응답 콘텐츠
        
    Returns:
        list: 추출된 주문 목록
    """
    orders = []
    
    # time_based_orders 배열 추출 시도
    time_orders_match = re.search(r'"time_based_orders"\s*:\s*\[(.*?)\]', content, re.DOTALL)
    if time_orders_match:
        orders_text = time_orders_match.group(1)
        # 각 주문 객체 추출
        order_objects = re.findall(r'\{(.*?)\}', orders_text, re.DOTALL)
        
        for order_obj in order_objects:
            order = {}
            # 각 필드 추출
            time_match = re.search(r'"time"\s*:\s*"([^"]*)"', order_obj)
            customer_match = re.search(r'"customer"\s*:\s*"([^"]*)"', order_obj)
            item_match = re.search(r'"item"\s*:\s*"([^"]*)"', order_obj)
            quantity_match = re.search(r'"quantity"\s*:\s*"?(\d+)"?', order_obj)
            delivery_date_match = re.search(r'"delivery_date"\s*:\s*"([^"]*)"', order_obj)
            note_match = re.search(r'"note"\s*:\s*"([^"]*)"', order_obj)
            
            if time_match:
                order["time"] = time_match.group(1)
            if customer_match:
                order["customer"] = customer_match.group(1)
            if item_match:
                order["item"] = item_match.group(1)
            if quantity_match:
                order["quantity"] = quantity_match.group(1)
            if delivery_date_match:
                order["delivery_date"] = delivery_date_match.group(1)
            if note_match:
                order["note"] = note_match.group(1)
            
            # 최소한 주문자와 상품은 있어야 함
            if "customer" in order and "item" in order:
                # 아이템 유효성 검사 추가
                if is_valid_item_name(order["item"]):
                    orders.append(order)
    
    return orders

def extract_orders_directly(conversation_text):
    """
    대화 내용에서 직접 주문 정보를 추출합니다.
    
    Args:
        conversation_text (str): 대화 내용
        
    Returns:
        list: 추출된 주문 목록
    """
    orders = []
    lines = conversation_text.split('\n')
    
    # 판매자 메시지에서 판매 상품 정보 추출
    product_info = extract_product_info_from_seller_messages(conversation_text)
    available_products = get_available_products(conversation_text)
    
    print(f"추출된 판매 상품 정보: {len(available_products)}개 상품 발견")
    
    current_date = None
    current_time = None
    delivery_date = None  # 수령일 정보
    
    # 대략적인 날짜/시간 패턴
    date_pattern = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'
    time_pattern = r'(오전|오후)\s*(\d{1,2}):(\d{2})'
    
    # 판매자 식별 패턴
    seller_pattern = "|".join(SELLER_KEYWORDS)
    
    # 주문 패턴 (다양한 형식 포함) - 더 정확한 패턴 사용
    # 기본 패턴: [닉네임] [전화번호 뒷자리] [상품명] [수량]
    # 구분자는 '/', ',', ':', ' ' 등이 사용될 수 있음
    order_pattern = r'([가-힣a-zA-Z0-9_/\s\-\(\)\♡\★\☆\♥\😊\👍\d]+)(?:\s*[/,:：]\s*)?' + \
                    r'(?:(\d{3,4})(?:\s*[/,:：]\s*))?' + \
                    r'([가-힣a-zA-Z0-9\s]{2,}[가-힣a-zA-Z]+)\s*(\d+)(?:개|팩|세트|병|봉)?'
                    
    # 수령일 정보 패턴
    delivery_date_pattern = r'수령일[:\s]*([월화수목금토일]\s*요일|[월화수목금토일](?:,\s*[월화수목금토일])*)'
    
    # 판매자 메시지에서 수령일 정보 추출
    for category, products in product_info.items():
        for product in products:
            if "deadline" in product:
                # 판매자가 언급한 수령일 저장
                for line in lines:
                    if re.search(seller_pattern, line) and product["name"] in line and ("수령일" in line or "수령" in line):
                        pickup_match = re.search(r'(?:수령일?|픽업|도착)(?:은|는)?\s*(\d+월\s*\d+일|\d+일|[월화수목금토일]요일|내일|오늘|다음주|이번주)', line)
                        if pickup_match:
                            product["delivery_date"] = pickup_match.group(1)
                            break
    
    processed_orders = {}  # 중복 주문 방지를 위한 딕셔너리
    
    for i, line in enumerate(lines):
        # 날짜 패턴 검색
        date_match = re.search(date_pattern, line)
        if date_match:
            year, month, day = date_match.groups()
            current_date = f"{year}년 {month}월 {day}일"
            continue  # 날짜 정보만 있는 라인은 주문으로 처리하지 않음
        
        # 시간 패턴 검색
        time_match = re.search(time_pattern, line)
        if time_match:
            ampm, hour, minute = time_match.groups()
            current_time = f"{ampm} {hour}:{minute}"
        
        # 수령일 정보 검색
        delivery_match = re.search(delivery_date_pattern, line)
        if delivery_match:
            delivery_date = delivery_match.group(1)
            print(f"수령일 정보 발견: {delivery_date}")
            continue  # 수령일 정보만 있는 라인은 주문으로 처리하지 않음
        
        # 판매자 메시지는 건너뛰기
        if re.search(seller_pattern, line):
            # 하지만 수령일 정보가 있는지 확인
            if "수령일" in line or "픽업일" in line:
                delivery_date_match = re.search(r'(수령일|픽업일)[:\s]*([월화수목금토일]\s*요일|[월화수목금토일](?:,\s*[월화수목금토일])*)', line)
                if delivery_date_match:
                    delivery_date = delivery_date_match.group(2)
                    print(f"판매자 메시지에서 수령일 정보 발견: {delivery_date}")
            continue
        
        # 주문 패턴 검색
        order_matches = re.findall(order_pattern, line)
        
        for match in order_matches:
            customer_name, phone_number, item, quantity = match
            
            # 쓸데없는 공백 제거 및 정리
            customer_name = customer_name.strip()
            item = item.strip()
            quantity = quantity.strip()
            
            # 품목명 유효성 검증 - 판매 상품 목록 활용
            if not is_valid_item_name(item, available_products):
                continue
                
            # 전화번호가 있으면 닉네임에 추가
            if phone_number:
                customer = f"{customer_name} {phone_number}"
            else:
                customer = customer_name
            
            # 품목에 맞는 수령일 찾기
            item_delivery_date = delivery_date
            for category, products in product_info.items():
                for product in products:
                    if product["name"].lower() in item.lower() or item.lower() in product["name"].lower():
                        if "delivery_date" in product and product["delivery_date"]:
                            item_delivery_date = product["delivery_date"]
                            break
            
            # 중복 주문 확인 - 같은 고객이 같은 시간에 같은 상품을 주문한 경우에는 수량만 합산
            order_key = f"{customer}:{item}:{current_time}"
            if order_key in processed_orders:
                try:
                    # 기존 주문에 수량 추가
                    prev_qty = int(processed_orders[order_key]["quantity"])
                    new_qty = int(quantity) if quantity else 1
                    processed_orders[order_key]["quantity"] = str(prev_qty + new_qty)
                    print(f"중복 주문 감지: {customer}의 {item} - 수량 합산: {prev_qty} + {new_qty}")
                    continue
                except ValueError:
                    # 숫자 변환 실패 시 새 주문으로 처리
                    pass
            
            # 주문 객체 생성
            order = {
                "time": current_time or "",
                "customer": customer,
                "item": item,
                "quantity": quantity,
                "delivery_date": item_delivery_date or "",
                "note": ""
            }
            
            # 취소 주문 처리
            if "취소" in line or "취소해" in line or "취소합" in line:
                order["note"] = "취소 요청"
                print(f"취소 주문 감지: {customer}의 {item} {quantity}개")
            
            # 변경 주문 처리
            elif "변경" in line:
                order["note"] = "변경 요청"
                print(f"변경 주문 감지: {customer}의 {item} {quantity}개")
            
            processed_orders[order_key] = order
    
    # 처리된 주문을 리스트로 변환
    orders = list(processed_orders.values())
    
    print(f"직접 추출 결과: {len(orders)}개 주문 추출됨")
    return orders

def extract_product_info_from_seller_messages(conversation_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    판매자 메시지에서 판매 상품 정보를 추출합니다.
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: 카테고리별 상품 정보
    """
    lines = conversation_text.split('\n')
    product_info = {category: [] for category in PRODUCT_CATEGORIES.keys()}
    
    current_date = None
    is_seller_block = False
    seller_block = []
    
    # 로그 추가
    print(f"대화 내용 총 {len(lines)}줄 분석 중...")
    seller_lines_count = 0
    
    # 판매자 메시지 블록 식별 및 추출
    for i, line in enumerate(lines):
        # 날짜 정보 추출
        date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', line)
        if date_match:
            year, month, day = date_match.groups()
            current_date = f"{year}년 {month}월 {day}일"
            if is_seller_block and seller_block:
                process_seller_block(seller_block, product_info, current_date)
                seller_block = []
            is_seller_block = False
            continue
        
        # 카카오톡 메시지 형식: "시간, 이름 : 내용" 패턴 확인
        message_match = re.search(r'(\d{4})년\s*\d{1,2}월\s*\d{1,2}일\s*(오전|오후)\s*(\d{1,2}):(\d{2}),\s*([^:]+)\s*:\s*(.*)', line)
        if message_match:
            # 새로운 메시지 시작, 이전 판매자 블록 처리
            if is_seller_block and seller_block:
                process_seller_block(seller_block, product_info, current_date)
                seller_block = []
                is_seller_block = False
                
            # 현재 메시지가 판매자 메시지인지 확인
            sender = message_match.group(5).strip()
            content = message_match.group(6).strip()
            
            # 판매자 키워드 확인 - 메시지 발신자 이름에 키워드가 있는지
            is_seller_line = any(keyword in sender for keyword in SELLER_KEYWORDS)
            
            if is_seller_line:
                seller_lines_count += 1
                is_seller_block = True
                full_message = f"{sender} : {content}"
                seller_block.append(full_message)
                # 디버깅을 위해 판매자 메시지 로깅
                if len(seller_block) <= 3:  # 처음 몇 개만 로깅
                    print(f"판매자 메시지 감지: {full_message[:50]}...")
            
            continue
        
        # 기존 판매자 블록에 내용 추가 (메시지 본문이 여러 줄인 경우)
        if is_seller_block:
            seller_block.append(line)
    
    # 마지막 판매자 블록 처리
    if is_seller_block and seller_block:
        process_seller_block(seller_block, product_info, current_date)
    
    # 추출 결과 로깅
    total_products = sum(len(products) for products in product_info.values())
    print(f"판매자 메시지 {seller_lines_count}개 분석, 총 {total_products}개 상품 정보 추출")
    
    for category, products in product_info.items():
        if products:
            product_names = [p['name'] for p in products]
            print(f"  - {category}: {', '.join(product_names)}")
    
    return product_info

def process_seller_block(seller_block: List[str], product_info: Dict[str, List[Dict[str, Any]]], current_date: str):
    """
    판매자 메시지 블록을 처리하여 상품 정보를 추출합니다.
    
    Args:
        seller_block (List[str]): 판매자 메시지 블록
        product_info (Dict[str, List[Dict[str, Any]]]): 추출된 상품 정보
        current_date (str): 현재 날짜
    """
    # 판매자 블록 전체를 하나의 문자열로 결합
    block_text = "\n".join(seller_block)
    
    # 디버깅을 위한 메시지 블록 내용 출력 (처음 200자만)
    print(f"판매자 블록 분석 중 (길이: {len(block_text)}자)")
    print(f"블록 내용 미리보기: {block_text[:200]}...")
    
    # 마감 시간 정보 추출
    deadline_info = extract_deadline_info(block_text)
    if deadline_info:
        print(f"마감 정보 {len(deadline_info)}개 발견")
    
    # 가격 정보 추출 - 다양한 패턴을 포함하도록 개선
    price_patterns = [
        r'(?:➡️|→)?\s*(?:아무거나)?\s*(\d+)(?:팩|세트|개|통|봉|박스|꼬치)?\s*(\d{1,3}(?:,\d{3})*)\s*원',  # 기본 패턴
        r'(\d+)(?:팩|세트|개|통|봉|박스|꼬치)\s*(\d{1,3}(?:,\d{3})*)\s*원',  # 팩/세트 + 가격
        r'(\d+)(?:팩|세트|개|통|봉|박스|꼬치)?\s*(?:→|➡️)?\s*(\d{1,3}(?:,\d{3})*)\s*원',  # 화살표 기호 포함
        r'(\d+)(?:팩|세트|개|통|봉|박스|꼬치)?\s+(\d{3,5})',  # 수량 + 숫자(가격) 패턴
        r'(\d+)(?:팩|세트|개|통|봉|박스|꼬치)?\s*(\d{1,3}(?:,\d{3})*)'  # 수량 + 가격(원 표시 없음)
    ]
    
    all_prices = []
    for pattern in price_patterns:
        prices = re.findall(pattern, block_text)
        all_prices.extend(prices)
    
    if all_prices:
        print(f"가격 정보 {len(all_prices)}개 발견")
    
    # 추가 상품 이름 패턴 (카테고리에 정의되지 않았지만 자주 등장하는 상품)
    additional_product_patterns = [
        (r'(?:초코|고구마)(?:생크림)?케이?[크익]', "케이크"),
        (r'하이드로겔\s*(?:마스크팩|시트)', "마스크팩"),
        (r'송화버섯[해장]?국', "곰탕"),
        (r'치즈부대찌개', "불고기"),
        (r'프리미엄\s*(?:하이드로겔|마스크팩)', "마스크팩")
    ]
    
    # 각 카테고리별로 상품 정보 추출
    extracted_products = []
    
    # 카테고리 패턴 기반 추출
    for category, patterns in PRODUCT_CATEGORIES.items():
        for pattern in patterns:
            matches = re.finditer(pattern, block_text, re.IGNORECASE)
            for match in matches:
                product_name = match.group(0)
                
                # 해당 상품의 가격 찾기
                price = None
                for qty, prc in all_prices:
                    # 상품명 주변 텍스트에서 가격 찾기
                    context_start = max(0, match.start() - 100)
                    context_end = min(len(block_text), match.end() + 100)
                    context = block_text[context_start:context_end]
                    if qty and prc and (qty in context and prc in context):
                        price = prc.replace(",", "")
                        break
                
                # 마감 정보 찾기
                deadline = None
                for prod, dead in deadline_info:
                    if prod in product_name or product_name in prod:
                        deadline = dead
                        break
                
                # 수령일 정보 찾기 (추가)
                delivery_date = None
                delivery_match = re.search(r'(?:수령일?|픽업|도착)(?:은|는)?\s*(\d+월\s*\d+일|\d+일|[월화수목금토일]요일|내일|오늘|다음주|이번주)', block_text)
                if delivery_match:
                    delivery_date = delivery_match.group(1)
                
                # 상품 정보 저장
                product_entry = {
                    "name": product_name,
                    "category": category,
                    "price": price,
                    "deadline": deadline,
                    "delivery_date": delivery_date,
                    "date": current_date
                }
                
                # 중복 방지
                if not any(p["name"] == product_name for p in product_info[category]):
                    product_info[category].append(product_entry)
                    extracted_products.append(product_name)
    
    # 추가 패턴으로 상품 검색
    for pattern, category in additional_product_patterns:
        matches = re.finditer(pattern, block_text, re.IGNORECASE)
        for match in matches:
            product_name = match.group(0)
            
            # 해당 상품의 가격 찾기
            price = None
            for qty, prc in all_prices:
                # 상품명 주변 텍스트에서 가격 찾기
                context_start = max(0, match.start() - 100)
                context_end = min(len(block_text), match.end() + 100)
                context = block_text[context_start:context_end]
                if qty and prc and (qty in context and prc in context):
                    price = prc.replace(",", "")
                    break
            
            # 마감 정보 찾기
            deadline = None
            for prod, dead in deadline_info:
                if prod in product_name or product_name in prod:
                    deadline = dead
                    break
            
            # 수령일 정보 찾기
            delivery_date = None
            delivery_match = re.search(r'(?:수령일?|픽업|도착)(?:은|는)?\s*(\d+월\s*\d+일|\d+일|[월화수목금토일]요일|내일|오늘|다음주|이번주)', block_text)
            if delivery_match:
                delivery_date = delivery_match.group(1)
            
            # 상품 정보 저장
            if category in product_info:
                product_entry = {
                    "name": product_name,
                    "category": category,
                    "price": price,
                    "deadline": deadline,
                    "delivery_date": delivery_date,
                    "date": current_date
                }
                
                
                # 중복 방지
                if not any(p["name"] == product_name for p in product_info[category]):
                    product_info[category].append(product_entry)
                    extracted_products.append(product_name)
    
    # 블록별 추출 결과 로깅
    if extracted_products:
        print(f"블록에서 {len(extracted_products)}개 상품 추출: {', '.join(extracted_products[:5])}{'...' if len(extracted_products) > 5 else ''}")
    else:
        print("블록에서 상품 정보를 추출하지 못했습니다.")
    
    return product_info

def extract_deadline_info(text: str) -> List[Tuple[str, str]]:
    """
    상품 마감 정보를 추출합니다.
    
    Args:
        text (str): 텍스트
        
    Returns:
        List[Tuple[str, str]]: (상품명, 마감시간) 튜플의 리스트
    """
    deadline_info = []
    
    # 마감 정보 패턴
    patterns = [
        r'([가-힣a-zA-Z0-9\s]+)\s*➡️\s*([가-힣a-zA-Z0-9\s:]+마감)',
        r'([가-힣a-zA-Z0-9\s]+)\s*❌❌마감❌❌',
        r'([가-힣a-zA-Z0-9\s]+)\s*(?:➡|→)\s*([가-힣0-9\s:]+마감)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple) and len(match) >= 2:
                product, deadline = match[0].strip(), match[1].strip()
                deadline_info.append((product, deadline))
            elif isinstance(match, str):
                product = match.strip()
                deadline_info.append((product, "마감"))
    
    return deadline_info

def get_available_products(conversation_text: str) -> Set[str]:
    """
    대화 내용에서 현재 주문 가능한 상품 목록을 추출합니다.
    
    Args:
        conversation_text (str): 카카오톡 대화 내용
        
    Returns:
        Set[str]: 주문 가능한 상품명 집합
    """
    product_info = extract_product_info_from_seller_messages(conversation_text)
    available_products = set()
    
    for category, products in product_info.items():
        for product in products:
            # "마감" 문구가 있는 상품은 제외
            if product.get("deadline") and "❌❌마감❌❌" in product["deadline"]:
                continue
            
            available_products.add(product["name"])
            # 상품명 변형도 추가 (검색 용이성 향상)
            for pattern in PRODUCT_CATEGORIES[category]:
                pattern_match = re.search(pattern, product["name"])
                if pattern_match:
                    available_products.add(pattern_match.group(0))
    
    return available_products

from typing import List, Dict, Any, Set, Optional

def is_valid_item_name(item_name: str) -> bool:
    """
    품목명이 유효한지 검증합니다.
    
    Args:
        item_name: 검증할 품목명
        
    Returns:
        유효한 품목명이면 True, 아니면 False
    """
    if not item_name or len(item_name.strip()) < 2:
        return False
        
    # 너무 긴 품목명 제한
    if len(item_name) > 50:
        return False
        
    # 판매 품목으로 적합하지 않은 단어 필터링
    invalid_keywords = [
        "안녕", "네", "오늘", "내일", "작성", "일정", "배송", "입금", "마감", "확인",
        "주말", "감사", "연락", "안내", "공지", "판매", "전달", "변경", "추가", "픽업"
    ]
    
    # 단독으로 사용된 경우만 필터링
    if item_name.strip() in invalid_keywords:
        return False
        
    return True

def is_valid_order_format(order: Dict[str, Any]) -> bool:
    """
    주문 형식이 유효한지 검증합니다.
    
    Args:
        order: 검증할 주문 데이터
        
    Returns:
        유효하면 True, 아니면 False
    """
    required_fields = ["customer", "item", "quantity"]
    for field in required_fields:
        if field not in order:
            print(f"주문 검증 실패: '{field}' 필드 누락")
            return False
    
    # 수량 검증
    try:
        quantity = order.get("quantity")
        if quantity is not None:
            if isinstance(quantity, str):
                # 문자열 수량을 숫자로 변환 시도
                quantity = quantity.replace(",", "").strip()
                int(quantity)
            else:
                # 이미 숫자 타입인지 확인
                int(quantity)
    except ValueError:
        print(f"주문 검증 실패: 잘못된 수량 형식 - '{order.get('quantity')}'")
        return False
    
    return True

def validate_analysis_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    분석 결과를 검증하고 필수 필드가 없으면 생성합니다.
    
    Args:
        result: 검증할 분석 결과
        
    Returns:
        검증 및 수정된 분석 결과
    """
    if not result:
        result = {}
    
    # 필수 필드 확인
    required_fields = [
        "time_based_orders", 
        "item_based_summary", 
        "customer_based_orders", 
        "table_summary", 
        "order_pattern_analysis"
    ]
    
    for field in required_fields:
        if field not in result:
            print(f"⚠️ 경고: {field} 필드가 응답에 없습니다!")
            
            if field == "time_based_orders":
                result[field] = []
            elif field == "item_based_summary":
                result[field] = []
            elif field == "customer_based_orders":
                result[field] = []
            elif field == "table_summary":
                result[field] = {
                    "headers": [],
                    "rows": []
                }
            elif field == "order_pattern_analysis":
                result[field] = {
                    "peak_hours": [],
                    "popular_items": [],
                    "sold_out_items": []
                }
    
    # 필드 내부 구조 검증
    if "table_summary" in result and isinstance(result["table_summary"], dict):
        if "headers" not in result["table_summary"]:
            result["table_summary"]["headers"] = []
        if "rows" not in result["table_summary"]:
            result["table_summary"]["rows"] = []
            
        # 테이블 요약에서 '등 다수' 처리 - 품목별 요약에서 완전한 주문자 목록 가져오기
        if "item_based_summary" in result and "rows" in result["table_summary"]:
            item_to_customers = {}
            
            # 품목별 요약에서 주문자 목록 추출
            for item_summary in result["item_based_summary"]:
                if "item" in item_summary and "customers" in item_summary:
                    item_to_customers[item_summary["item"]] = item_summary["customers"]
            
            # 행별로 '등 다수' 제거하고 완전한 주문자 목록으로 대체
            for i, row in enumerate(result["table_summary"]["rows"]):
                if len(row) >= 3:  # 품목, 수량, 주문자 컬럼이 있는지 확인
                    item_name = str(row[0])
                    if item_name in item_to_customers:
                        # '등 다수'가 있거나 주문자 수가 다를 경우 교체
                        current_customers = str(row[2])
                        full_customers = item_to_customers[item_name]
                        
                        if "등 다수" in current_customers or len(current_customers.split(',')) != len(full_customers.split(',')):
                            print(f"테이블 요약 수정: {item_name}의 주문자 목록을 완전한 목록으로 교체합니다.")
                            result["table_summary"]["rows"][i][2] = full_customers
    
    if "order_pattern_analysis" in result and isinstance(result["order_pattern_analysis"], dict):
        if "peak_hours" not in result["order_pattern_analysis"]:
            result["order_pattern_analysis"]["peak_hours"] = []
        if "popular_items" not in result["order_pattern_analysis"]:
            result["order_pattern_analysis"]["popular_items"] = []
        if "sold_out_items" not in result["order_pattern_analysis"]:
            result["order_pattern_analysis"]["sold_out_items"] = []
    
    return result

def filter_invalid_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    유효하지 않은 품목을 필터링합니다.
    
    Args:
        items: 품목 목록
        
    Returns:
        필터링된 품목 목록
    """
    filtered_items = []
    filtered_count = 0
    
    for item in items:
        # 'item' 필드가 있는 경우 품목명 검증
        if "item" in item and is_valid_item_name(item["item"]):
            filtered_items.append(item)
        # 'customer' 필드만 있는 경우 (customer_based_orders)
        elif "customer" in item and "item" not in item:
            filtered_items.append(item)
        else:
            filtered_count += 1
    
    if filtered_count > 0:
        print(f"품목 필터링: {filtered_count}개의 잘못된 품목명이 제외되었습니다.")
    
    return filtered_items

def validate_customer_name(customer_name: str) -> bool:
    """
    주문자명이 유효한지 검증합니다.
    
    Args:
        customer_name: 검증할 주문자명
        
    Returns:
        유효한 주문자명이면 True, 아니면 False
    """
    if not customer_name or len(customer_name.strip()) < 2:
        return False
    
    # 너무 긴 주문자명 제한
    if len(customer_name) > 20:
        return False
    
    # 주문자로 적합하지 않은 키워드 필터링
    invalid_keywords = [
        "안내", "공지", "판매", "배송", "마감", "주문", "픽업",
        "알림", "공구", "시작", "관리자", "사장님", "대표"
    ]
    
    for keyword in invalid_keywords:
        if keyword in customer_name:
            return False
    
    return True

def validate_quantity(quantity: Any) -> int:
    """
    수량을 검증하고 정수로 변환합니다.
    
    Args:
        quantity: 검증할 수량
        
    Returns:
        검증된 수량 (정수)
    """
    try:
        if isinstance(quantity, str):
            # 쉼표 제거 및 공백 제거
            quantity = quantity.replace(",", "").strip()
            return int(quantity)
        elif isinstance(quantity, (int, float)):
            return int(quantity)
        else:
            return 1
    except (ValueError, TypeError):
        return 1

def generate_table_summary(item_based_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    품목별 요약에서 테이블 요약을 생성합니다.
    이 함수는 모든 주문자를 완전히 표시하며 '등 다수'와 같은 축약 표현을 사용하지 않습니다.
    
    Args:
        item_based_summary: 품목별 요약 목록
    
    Returns:
        테이블 요약 데이터
    """
    table_summary = {
        "headers": ["품목", "총수량", "주문자"],
        "rows": []
    }
    
    # 품목별 요약을 수량 기준으로 내림차순 정렬
    sorted_items = sorted(
        item_based_summary, 
        key=lambda x: validate_quantity(x.get("total_quantity", 0)), 
        reverse=True
    )
    
    # 정렬된 품목별 요약에서 테이블 행 생성
    for item in sorted_items:
        item_name = item.get("item", "")
        if not item_name:
            continue
            
        total_quantity = validate_quantity(item.get("total_quantity", 0))
        
        # 주문자 목록을 콤마로 구분하여 가져오기
        customers = item.get("customers", "")
        
        # 테이블 행 추가
        row = [item_name, total_quantity, customers]
        table_summary["rows"].append(row)
    
    return table_summary

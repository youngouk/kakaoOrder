import base64
from typing import Dict, List, Any

def generate_csv_from_data(data: Dict[str, Any]) -> Dict[str, str]:
    """
    분석 데이터에서 CSV 파일을 생성합니다.
    
    Args:
        data: 분석 결과 데이터
        
    Returns:
        Base64로 인코딩된 CSV 데이터를 포함하는 딕셔너리
    """
    try:
        # CSV 헤더 매핑 정의
        time_header_map = {
            "time": "시간",
            "customer": "주문자",
            "item": "품목",
            "quantity": "수량",
            "note": "비고"
        }
        
        item_header_map = {
            "item": "품목명",
            "total_quantity": "총 수량",
            "customers": "주문자 목록"
        }
        
        customer_header_map = {
            "customer": "주문자",
            "item": "품목",
            "quantity": "수량",
            "note": "비고"
        }
        
        result = {}
        
        if "time_based_orders" in data:
            headers = ["time", "customer", "item", "quantity", "note"]
            csv_data = _to_csv(data["time_based_orders"], headers, time_header_map)
            result["time_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
        if "item_based_summary" in data:
            headers = ["item", "total_quantity", "customers"]
            csv_data = _to_csv(data["item_based_summary"], headers, item_header_map)
            result["item_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
        if "customer_based_orders" in data:
            headers = ["customer", "item", "quantity", "note"]
            csv_data = _to_csv(data["customer_based_orders"], headers, customer_header_map)
            result["customer_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
        return result
        
    except Exception as e:
        print(f"CSV 생성 중 오류 발생: {str(e)}")
        return {}

def _to_csv(data_list: List[Dict[str, Any]], headers: List[str], header_map: Dict[str, str]) -> str:
    """
    데이터 목록을 CSV 문자열로 변환합니다.
    
    Args:
        data_list: 변환할 데이터 목록
        headers: CSV 헤더 필드
        header_map: CSV 헤더 매핑 (영문 -> 한글)
        
    Returns:
        CSV 문자열
    """
    # CSV 헤더 추가
    header_row = []
    for h in headers:
        header_row.append(f'"{header_map[h]}"')
    
    rows = [",".join(header_row)]
    
    # 데이터 행 추가
    for item in data_list:
        row = []
        for h in headers:
            value = item.get(h, "")
            if isinstance(value, str):
                # 특수문자 처리
                value = value.replace('"', '""')
                row.append(f'"{value}"')
            else:
                row.append(f'"{str(value)}"')
        rows.append(",".join(row))
        
    return "\n".join(rows)

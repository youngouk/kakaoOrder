import json
import re
import concurrent.futures
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import traceback
import pathlib
import time

from utils.text_processing import (
    filter_conversation_by_date,
    split_conversation_into_chunks
)
from utils.validation import (
    is_valid_order_format,
    validate_analysis_result,
    filter_invalid_items,
    is_valid_item_name
)
from services.llm_service import analyze_conversation_chunk
from services.progress_tracker import EnhancedProgressLogger, ProgressPhase

# 진행상태 로그 클래스 추가
class ProgressLogger:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.logs = []
    
    def add_log(self, phase: str, details: List[str]):
        """진행상태 로그를 추가합니다"""
        log_entry = {
            "phase": phase,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.logs.append(log_entry)
        print(f"[{self.job_id}] {phase}: {', '.join(details)}")
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """현재까지의 모든 로그를 반환합니다"""
        return self.logs.copy()

def process_conversation(
    conversation_text: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    shop_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    대화 내용을 분석하여 주문 정보를 추출합니다.
    
    Args:
        conversation_text: 대화 내용
        start_date: 시작일 (ISO 형식)
        end_date: 종료일 (ISO 형식)
        shop_name: 상점 이름
        
    Returns:
        분석 결과
    """
    try:
        print(f"Starting analysis: shop_name={shop_name}, start_date={start_date}, end_date={end_date}")
        print(f"Conversation length: {len(conversation_text)} characters")
        
        # 날짜 범위로 대화 필터링
        if start_date or end_date:
            conversation_text = filter_conversation_by_date(conversation_text, start_date, end_date)
            print(f"Filtered conversation length: {len(conversation_text)} characters")
        
        # LLM을 통한 대화 분석
        result = analyze_conversation_with_llm_improved(conversation_text, shop_name)
        
        # 결과 검증 및 보정
        result = validate_analysis_result(result)
        
        # 잘못된 품목 필터링 - time_based_orders에만 적용
        # (item_based_summary와 customer_based_orders는 regenerate_summaries_from_time_based에서 이미 처리됨)
        if "time_based_orders" in result:
            result["time_based_orders"] = filter_invalid_items(result["time_based_orders"])
            
        # 매장명 정보 추가
        if shop_name:
            result["shop_name"] = shop_name
            
        print(f"분석 완료: {len(result.get('time_based_orders', []))}개 주문, {len(result.get('item_based_summary', []))}개 품목")
        return result
        
    except Exception as e:
        print(f"대화 분석 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return {
            "error": True,
            "message": str(e)
        }

def analyze_conversation_with_llm_improved(conversation_text: str, shop_name: Optional[str] = None) -> Dict[str, Any]:
    """
    개선된 LLM 대화 분석 함수. 긴 대화는 청크로 나누어 병렬 처리하고, 시간 기반 정렬 및 취소 내역을 처리합니다.
    
    Args:
        conversation_text: 대화 내용
        shop_name: 상점 이름
        
    Returns:
        분석 결과
    """
    # 대화가 길 경우 여러 청크로 분할하여 처리
    if len(conversation_text) > 32000:
        print(f"대화가 너무 깁니다({len(conversation_text)} 자). 여러 청크로 분할합니다.")
        chunks = split_conversation_into_chunks(conversation_text)
        print(f"{len(chunks)}개의 청크로 분할되었습니다.")
        
        # 병렬 처리를 위한 스레드 풀 생성
        chunk_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(chunks), 5)) as executor:
            future_to_chunk = {
                executor.submit(analyze_conversation_chunk, chunk, shop_name): i 
                for i, chunk in enumerate(chunks)
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    result = future.result()
                    print(f"청크 {chunk_index} 분석 완료")
                    chunk_results.append(result)
                except Exception as e:
                    print(f"청크 {chunk_index} 분석 중 오류: {str(e)}")
        
        # 시간순 정렬 후 time_based_orders만 추출
        time_sorted_result = merge_chunk_results_improved(chunk_results)
        
        # 중간 결과 저장 (선택적)
        save_sorted_time_based_orders(time_sorted_result, shop_name)
        
        # 정렬된 time_based_orders에서 요약 정보 재생성
        time_based_orders = time_sorted_result.get("time_based_orders", [])
        summary_result = regenerate_summaries_from_time_based(time_based_orders)
        
        # 최종 결과 조합
        final_result = {
            "time_based_orders": time_based_orders,
            "customer_based_orders": summary_result["customer_based_orders"],
            "item_based_summary": summary_result["item_based_summary"],
            "table_summary": summary_result["table_summary"],
            "order_pattern_analysis": time_sorted_result.get("order_pattern_analysis", {})
        }
        
        # 매장명 정보 추가
        if shop_name:
            final_result["shop_name"] = shop_name
            
        print(f"개선된 분석 완료: {len(final_result.get('time_based_orders', []))}개 주문")
        return final_result
    else:
        # 단일 청크로 처리 (기존 로직 유지)
        return analyze_conversation_chunk(conversation_text, shop_name)

def merge_chunk_results_improved(chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    개선된 청크 병합 함수: time_based_orders만 시간순 정렬 후 병합
    
    Args:
        chunk_results: 청크별 분석 결과 목록
        
    Returns:
        시간순 정렬된 time_based_orders를 포함한 병합 결과
    """
    if not chunk_results:
        return {}
        
    # 첫 번째 결과를 기준으로 병합 템플릿 생성
    merged_result = chunk_results[0].copy()
    
    # time_based_orders 모든 청크에서 추출
    all_time_based_orders = []
    for result in chunk_results:
        if "time_based_orders" in result and isinstance(result["time_based_orders"], list):
            all_time_based_orders.extend(result["time_based_orders"])
    
    # 시간 기준으로 정렬 (오전/오후 고려)
    def time_sort_key(order):
        time_str = order.get("time", "")
        is_pm = "오후" in time_str
        
        # 시간 문자열에서 시:분 추출
        parts = time_str.replace("오전 ", "").replace("오후 ", "").split(":")
        if len(parts) != 2:
            return (0, 0)  # 잘못된 형식은 맨 앞으로
            
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            
            # 오후는 12시간 추가 (오후 12시 제외)
            if is_pm and hour < 12:
                hour += 12
                
            return (hour, minute)
        except:
            return (0, 0)
    
    # 시간순 정렬
    all_time_based_orders.sort(key=time_sort_key)
    
    # time_based_orders를 정렬된 것으로 교체
    merged_result["time_based_orders"] = all_time_based_orders
    
    # order_pattern_analysis 병합 (기존 로직 유지)
    if "order_pattern_analysis" in merged_result:
        for result in chunk_results[1:]:
            if "order_pattern_analysis" not in result:
                continue
                
            # 피크 시간 병합
            if "peak_hours" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["peak_hours"] = merged_result["order_pattern_analysis"].get("peak_hours", [])
                merged_result["order_pattern_analysis"]["peak_hours"].extend(result["order_pattern_analysis"]["peak_hours"])
                
            # 인기 상품 병합
            if "popular_items" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["popular_items"] = merged_result["order_pattern_analysis"].get("popular_items", [])
                merged_result["order_pattern_analysis"]["popular_items"].extend(result["order_pattern_analysis"]["popular_items"])
                
            # 품절 상품 병합
            if "sold_out_items" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["sold_out_items"] = merged_result["order_pattern_analysis"].get("sold_out_items", [])
                merged_result["order_pattern_analysis"]["sold_out_items"].extend(result["order_pattern_analysis"]["sold_out_items"])
    
    print(f"시간순 정렬 병합 완료: {len(merged_result.get('time_based_orders', []))}개 주문")
    return merged_result

def regenerate_summaries_from_time_based(time_based_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    정렬된 time_based_orders에서 취소 내역을 반영한 요약 정보 생성
    
    Args:
        time_based_orders: 시간순 정렬된 주문 목록
        
    Returns:
        취소 내역이 반영된 요약 정보
    """
    # 디버깅 정보 출력
    print(f"\n=== regenerate_summaries_from_time_based 시작 ===")
    print(f"입력 받은 주문 수: {len(time_based_orders)}개")
    
    # 고객별 최종 주문 상태 추적
    customer_orders = {}
    item_summary = {}
    
    # 디버깅용 카운터
    processed_count = 0
    cancelled_count = 0
    invalid_count = 0
    
    # 각 주문을 시간순으로 처리하며 취소 내역 반영
    for idx, order in enumerate(time_based_orders):
        customer = order.get("customer", "")
        item = order.get("item", "")
        quantity = order.get("quantity", 0)
        note = order.get("note", "").lower() if order.get("note") else ""
        
        # 데이터 검증
        if not customer or not item:
            invalid_count += 1
            print(f"  주문 {idx}: 고객명 또는 품목명 누락 - customer: '{customer}', item: '{item}'")
            continue
        
        # 수량이 문자열인 경우 정수로 변환
        if isinstance(quantity, str):
            try:
                quantity = int(quantity.replace(",", ""))
            except:
                quantity = 1
                
        # 취소 요청 확인 (노트나 품목명에 '취소' 포함)
        is_cancellation = "취소" in note or "취소" in item
        
        # 취소 주문인 경우 이전 주문에서 차감
        if is_cancellation:
            cancelled_count += 1
            # 취소 대상 품목 찾기
            target_item = item.replace("취소", "").strip()
            if not target_item and customer in customer_orders:
                # 특정 품목 지정 없이 취소한 경우 해당 고객의 모든 주문 취소
                print(f"고객 '{customer}'의 모든 주문이 취소되었습니다.")
                customer_orders[customer] = []
            elif target_item:
                # 특정 품목 취소 - 해당 고객의 해당 품목 주문 찾기
                if customer in customer_orders:
                    before_count = len(customer_orders[customer])
                    customer_orders[customer] = [
                        o for o in customer_orders[customer] 
                        if o.get("item") != target_item
                    ]
                    after_count = len(customer_orders[customer])
                    print(f"고객 '{customer}'의 '{target_item}' 주문이 취소되었습니다. ({before_count-after_count}개 항목 제거)")
        else:
            # 일반 주문 처리
            if customer not in customer_orders:
                customer_orders[customer] = []
                
            # 해당 고객의 같은 품목 주문이 있는지 확인
            found = False
            for existing_order in customer_orders[customer]:
                if existing_order.get("item") == item:
                    # 기존 주문에 수량 추가
                    existing_order["quantity"] = existing_order.get("quantity", 0) + quantity
                    found = True
                    break
                    
            if not found:
                # 새 주문 추가
                customer_orders[customer].append({
                    "item": item,
                    "quantity": quantity,
                    "note": note
                })
        
        processed_count += 1
    
    # 고객별 주문으로부터 customer_based_orders 생성
    customer_based_orders = []
    for customer, orders in customer_orders.items():
        if not orders:  # 모든 주문이 취소된 고객 제외
            continue
        
        # 각 주문 항목을 개별 행으로 추가
        for order in orders:
            customer_based_orders.append({
                "customer": customer,
                "item": order.get("item", ""),
                "quantity": order.get("quantity", 0),
                "note": order.get("note", "")
            })
    
    # 품목별 요약 생성 (고객 중복 제거를 위해 set 사용)
    item_customers = {}  # 품목별 고객 set 저장
    
    for customer, orders in customer_orders.items():
        for order in orders:
            item = order.get("item")
            quantity = order.get("quantity", 0)
            
            if not item or quantity <= 0:
                continue
                
            if item not in item_summary:
                item_summary[item] = {
                    "item": item,
                    "total_quantity": 0,
                    "customers": ""
                }
                item_customers[item] = set()
                
            item_summary[item]["total_quantity"] += quantity
            item_customers[item].add(customer)
    
    # 고객 목록을 문자열로 변환
    for item in item_summary:
        if item in item_customers:
            item_summary[item]["customers"] = ", ".join(sorted(item_customers[item]))
    
    # 테이블 요약 생성
    table_rows = []
    for item, summary in item_summary.items():
        table_rows.append([
            item,
            summary["total_quantity"],
            summary["customers"]
        ])
    
    table_summary = {
        "headers": ["품목", "총 수량", "주문자"],
        "rows": table_rows
    }
    
    print(f"\n=== regenerate_summaries_from_time_based 결과 ===")
    print(f"처리된 주문: {processed_count}개")
    print(f"취소된 주문: {cancelled_count}개") 
    print(f"무효 주문: {invalid_count}개")
    print(f"총 고객 수: {len(customer_orders)}명")
    print(f"총 품목 수: {len(item_summary)}개")
    print(f"요약 정보 재생성: {len(customer_based_orders)}명의 고객, {len(item_summary)}개 품목")
    
    # 품목별 상세 정보 출력 (디버깅용)
    if len(item_summary) < 20:  # 품목이 너무 많지 않으면 상세 출력
        print("\n품목별 상세:")
        for item_name, summary in item_summary.items():
            print(f"  - {item_name}: {summary['total_quantity']}개")
    
    return {
        "customer_based_orders": customer_based_orders,
        "item_based_summary": list(item_summary.values()),
        "table_summary": table_summary
    }

def save_sorted_time_based_orders(result: Dict[str, Any], shop_name: Optional[str] = None) -> str:
    """
    시간순 정렬된 time_based_orders를 파일로 저장
    
    Args:
        result: 시간순 정렬된 결과
        shop_name: 상점 이름
        
    Returns:
        저장된 파일 경로
    """
    # 로그 저장 디렉토리 생성
    logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "analysis_results"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    shop_name_part = f"_{shop_name}" if shop_name else ""
    file_name = f"time_sorted_orders{shop_name_part}_{timestamp}.json"
    file_path = logs_dir / file_name
    
    # 파일로 저장
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            
        print(f"시간순 정렬된 주문 목록이 {file_path}에 저장되었습니다.")
    except Exception as e:
        print(f"파일 저장 중 오류 발생: {str(e)}")
        traceback.print_exc()
        
    return str(file_path)

# 기존 함수들은 그대로 유지 (호환성을 위해)
def analyze_conversation_with_llm(conversation_text: str, shop_name: Optional[str] = None) -> Dict[str, Any]:
    """
    LLM을 이용하여 대화를 분석합니다. 긴 대화는 청크로 나누어 병렬 처리합니다.
    
    Args:
        conversation_text: 대화 내용
        shop_name: 상점 이름
        
    Returns:
        분석 결과
    """
    # 개선된 함수로 대체
    return analyze_conversation_with_llm_improved(conversation_text, shop_name)

def merge_chunk_results(chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    여러 청크의 분석 결과를 병합합니다.
    
    Args:
        chunk_results: 청크별 분석 결과 목록
        
    Returns:
        병합된 결과
    """
    if not chunk_results:
        return {}
        
    # 첫 번째 결과를 기준으로 병합
    merged_result = chunk_results[0].copy()
    
    # 리스트 형태의 필드 병합
    list_fields = ["time_based_orders", "item_based_summary", "customer_based_orders"]
    for field in list_fields:
        merged_result[field] = merged_result.get(field, [])
        
        # 나머지 청크의 결과 병합
        for result in chunk_results[1:]:
            if field in result and isinstance(result[field], list):
                merged_result[field].extend(result[field])
    
    # item_based_summary 중복 제거 및 통합
    if "item_based_summary" in merged_result:
        item_summary = {}
        for item_entry in merged_result["item_based_summary"]:
            item_name = item_entry.get("item", "")
            if item_name:
                if item_name not in item_summary:
                    item_summary[item_name] = item_entry
                else:
                    # 수량 합산
                    current_qty = item_summary[item_name].get("total_quantity", 0)
                    additional_qty = item_entry.get("total_quantity", 0)
                    
                    try:
                        if isinstance(current_qty, str):
                            current_qty = int(current_qty.replace(",", ""))
                        if isinstance(additional_qty, str):
                            additional_qty = int(additional_qty.replace(",", ""))
                            
                        item_summary[item_name]["total_quantity"] = current_qty + additional_qty
                    except:
                        pass
                    
                    # 주문자 목록 합산
                    current_customers = item_summary[item_name].get("customers", "")
                    additional_customers = item_entry.get("customers", "")
                    
                    if current_customers and additional_customers:
                        item_summary[item_name]["customers"] = f"{current_customers}, {additional_customers}"
                    elif additional_customers:
                        item_summary[item_name]["customers"] = additional_customers
        
        merged_result["item_based_summary"] = list(item_summary.values())
    
    # 주문 패턴 분석 병합
    if "order_pattern_analysis" in merged_result:
        for result in chunk_results[1:]:
            if "order_pattern_analysis" not in result:
                continue
                
            # 피크 시간 병합
            if "peak_hours" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["peak_hours"] = merged_result["order_pattern_analysis"].get("peak_hours", [])
                merged_result["order_pattern_analysis"]["peak_hours"].extend(result["order_pattern_analysis"]["peak_hours"])
                
            # 인기 상품 병합
            if "popular_items" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["popular_items"] = merged_result["order_pattern_analysis"].get("popular_items", [])
                merged_result["order_pattern_analysis"]["popular_items"].extend(result["order_pattern_analysis"]["popular_items"])
                
            # 품절 상품 병합
            if "sold_out_items" in result["order_pattern_analysis"]:
                merged_result["order_pattern_analysis"]["sold_out_items"] = merged_result["order_pattern_analysis"].get("sold_out_items", [])
                merged_result["order_pattern_analysis"]["sold_out_items"].extend(result["order_pattern_analysis"]["sold_out_items"])
    
    print(f"분석 결과 병합 완료: {len(merged_result.get('time_based_orders', []))}개 주문")
    return merged_result

def summarize_items(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    주문 목록에서 품목별 요약을 생성합니다.
    
    Args:
        orders: 주문 목록
        
    Returns:
        품목별 요약 목록
    """
    item_summary = {}
    filtered_items_count = 0
    
    for order in orders:
        item = order.get("item", "")
        
        if not is_valid_item_name(item):
            filtered_items_count += 1
            continue
            
        quantity = order.get("quantity", 0)
        customer = order.get("customer", "")
        
        # 수량 변환
        if isinstance(quantity, str):
            try:
                quantity = int(quantity.replace(",", ""))
            except:
                quantity = 1
        
        # 품목 요약 생성 또는 업데이트
        if item not in item_summary:
            item_summary[item] = {
                "item": item,
                "total_quantity": quantity,
                "customers": customer
            }
        else:
            # 수량 합산
            item_summary[item]["total_quantity"] += quantity
            
            # 주문자 추가
            customer_entry = customer
            current_customers = item_summary[item].get("customers", "")
            
            if current_customers:
                item_summary[item]["customers"] = f"{current_customers}, {customer_entry}"
            else:
                item_summary[item]["customers"] = customer_entry
    
    if filtered_items_count > 0:
        print(f"품목 필터링: {filtered_items_count}개의 잘못된 품목명이 제외되었습니다.")
    
    return list(item_summary.values())

def test_cancellation_processing(time_based_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    주문 취소 처리 로직을 테스트하는 함수입니다.
    개발 및 디버깅 용도로만 사용하세요.
    
    Args:
        time_based_orders: 시간순 정렬된 주문 목록
        
    Returns:
        테스트 결과를 포함한 딕셔너리
    """
    print("\n=== 주문 취소 처리 테스트 시작 ===")
    
    # 원본 주문 출력
    print("\n원본 주문 목록:")
    for i, order in enumerate(time_based_orders):
        time = order.get("time", "시간 없음")
        customer = order.get("customer", "고객 없음")
        item = order.get("item", "품목 없음")
        quantity = order.get("quantity", "수량 없음")
        note = order.get("note", "")
        
        note_text = f", 비고: {note}" if note else ""
        print(f"{i+1}. {time} - {customer} - {item} {quantity}개{note_text}")
    
    # 취소 주문 식별
    cancellations = []
    for i, order in enumerate(time_based_orders):
        note = order.get("note", "").lower() if order.get("note") else ""
        item = order.get("item", "")
        
        is_cancellation = "취소" in note or "취소" in item
        if is_cancellation:
            cancellations.append({
                "index": i,
                "order": order,
                "target_item": item.replace("취소", "").strip()
            })
    
    # 취소 내역 출력
    if cancellations:
        print("\n식별된 취소 내역:")
        for i, cancel in enumerate(cancellations):
            order = cancel["order"]
            time = order.get("time", "시간 없음")
            customer = order.get("customer", "고객 없음")
            item = order.get("item", "품목 없음")
            target_item = cancel["target_item"]
            
            print(f"{i+1}. {time} - {customer} - 취소 대상: '{target_item or item}'")
    else:
        print("\n취소 내역이 없습니다.")
    
    # 요약 재생성 결과 확인
    summary_result = regenerate_summaries_from_time_based(time_based_orders)
    
    # 재생성된 요약 출력
    print("\n취소 반영 후 고객별 주문:")
    for i, customer_order in enumerate(summary_result["customer_based_orders"]):
        customer = customer_order.get("customer", "고객 없음")
        orders = customer_order.get("orders", "")
        print(f"{i+1}. {customer} - {orders}")
    
    print("\n취소 반영 후 품목별 요약:")
    for i, item_summary in enumerate(summary_result["item_based_summary"]):
        item = item_summary.get("item", "품목 없음")
        quantity = item_summary.get("total_quantity", 0)
        customers = item_summary.get("customers", "")
        print(f"{i+1}. {item} - {quantity}개 - 주문자: {customers}")
    
    print("\n=== 주문 취소 처리 테스트 완료 ===")
    
    return {
        "original_orders": time_based_orders,
        "cancellations": cancellations,
        "processed_result": summary_result
    }

def analyze_conversation_with_progress(
    conversation_text: str,
    job_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shop_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    진행상태를 추적하면서 대화를 분석합니다.
    """
    progress_logger = ProgressLogger(job_id)

def analyze_conversation_with_progress_callback(
    conversation_text: str,
    job_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shop_name: Optional[str] = None,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    진행상태를 추적하면서 대화를 분석합니다. (콜백 지원 버전)
    """
    # EnhancedProgressLogger 사용
    progress_logger = EnhancedProgressLogger(job_id, progress_callback)
    
    try:
        # 2. 날짜 필터링
        preprocessed_text = conversation_text
        if start_date or end_date:
            from utils.text_processing import filter_conversation_by_date
            filtered_text = filter_conversation_by_date(conversation_text, start_date, end_date)
            
            if filtered_text == "지정된 날짜 범위에 해당하는 대화가 없습니다.":
                return {
                    "error": True,
                    "message": "지정된 날짜 범위에 해당하는 대화가 없습니다.",
                    "progress_logs": progress_logger.get_logs()
                }
            
            preprocessed_text = filtered_text
        
        # 3. 대화 전처리
        try:
            from services.preprocess_chat import ChatPreprocessor
            chat_preprocessor = ChatPreprocessor()
            
            # 전처리 실행
            preprocessed_text = chat_preprocessor.preprocess_chat(preprocessed_text)
            
            # 1단계: 대화내용 전처리 완료 (10%)
            progress_logger.add_log(
                ProgressPhase.PREPROCESSING_COMPLETE,
                [
                    f"원본 대화: {len(conversation_text):,}자",
                    f"전처리 후: {len(preprocessed_text):,}자",
                    f"압축률: {len(preprocessed_text)/len(conversation_text)*100:.1f}%"
                ]
            )
            
        except Exception as e:
            # 전처리 오류 시에도 진행
            preprocessed_text = conversation_text
            progress_logger.add_log(
                ProgressPhase.PREPROCESSING_COMPLETE,
                [
                    f"전처리 중 오류 발생: {str(e)}",
                    f"원본 대화 사용: {len(preprocessed_text):,}자"
                ]
            )
        
        # 4. 상품 정보 추출
        try:
            from services.product_service import get_available_products, extract_product_info
            
            # 2단계: 주문가능 품목 분석 요청 시작 (15%)
            progress_logger.add_log(
                ProgressPhase.PRODUCT_ANALYSIS_START,
                ["판매자 메시지에서 상품 정보를 추출하고 있습니다..."]
            )
            
            # 상품 정보 추출
            product_info_dict = extract_product_info(preprocessed_text)
            all_product_names_from_info = set()
            
            if isinstance(product_info_dict, dict) and "products" in product_info_dict:
                for product_detail in product_info_dict.get("products", []):
                    if isinstance(product_detail, dict) and "name" in product_detail:
                        all_product_names_from_info.add(product_detail["name"])
            
            # 대체 방법으로 상품명 추출
            if not all_product_names_from_info:
                all_product_names_from_info = get_available_products(preprocessed_text)
            
            final_product_list_for_llm = all_product_names_from_info
            
            # 3단계: 주문가능 품목 응답 받음 (25%)
            product_list = list(final_product_list_for_llm)
            product_display = ", ".join(product_list[:10])
            if len(product_list) > 10:
                product_display += f" 외 {len(product_list) - 10}개"
            
            progress_logger.add_log(
                ProgressPhase.PRODUCT_ANALYSIS_COMPLETE,
                [
                    f"주문가능 총 {len(final_product_list_for_llm)}개",
                    f"품목 리스트: {product_display}"
                ]
            )
            
        except Exception as e:
            progress_logger.add_log(
                ProgressPhase.PRODUCT_ANALYSIS_COMPLETE,
                [
                    f"상품 추출 오류: {str(e)}",
                    "빈 상품 목록으로 진행"
                ]
            )
            final_product_list_for_llm = set()
        
        # 5. 메인 분석 시작
        # 4단계: 메인 분석(timebase)을 위한 LLM 호출 시작 (30%)
        progress_logger.add_log(
            ProgressPhase.MAIN_ANALYSIS_START,
            [
                f"대화 길이: {len(preprocessed_text):,}자",
                "LLM 분석을 시작합니다. 시간이 걸릴 수 있습니다."
            ]
        )
        
        # 타이머 시작 (동기적으로 처리)
        progress_logger.start_main_analysis_timer()
        
        # 청크 분할 확인 및 처리
        if len(preprocessed_text) > 10000:
            from utils.text_processing import split_conversation_into_chunks
            chunks = split_conversation_into_chunks(preprocessed_text)
            
            # 병렬 처리
            import concurrent.futures
            from services.llm_service import analyze_conversation_chunk
            
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(chunks), 5)) as executor:
                future_to_chunk = {
                    executor.submit(analyze_conversation_chunk, chunk, shop_name, final_product_list_for_llm): i 
                    for i, chunk in enumerate(chunks)
                }
                
                for future in concurrent.futures.as_completed(future_to_chunk):
                    chunk_index = future_to_chunk[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        print(f"청크 {chunk_index + 1} 분석 실패: {str(e)}")
            
            # 결과 병합
            merged_result = merge_chunk_results_improved(results)
            
        else:
            # 단일 청크 처리
            from services.llm_service import analyze_conversation_chunk
            merged_result = analyze_conversation_chunk(preprocessed_text, shop_name, final_product_list_for_llm)
        
        # 타이머 중지
        progress_logger.stop_main_analysis_timer()
        
        # 9단계: 메인 분석 응답 수신 (95%)
        progress_logger.add_log(
            ProgressPhase.MAIN_ANALYSIS_COMPLETE,
            [
                f"분석 완료",
                f"추출된 주문: {len(merged_result.get('time_based_orders', []))}개"
            ]
        )
        
        # 6. 최종 처리
        if "error" in merged_result:
            merged_result["progress_logs"] = progress_logger.get_logs()
            return merged_result
        
        # time_based_orders로부터 요약 정보 재생성
        time_based_orders = merged_result.get("time_based_orders", [])
        summary_result = regenerate_summaries_from_time_based(time_based_orders)
        
        # 최종 결과 조합
        merged_result["customer_based_orders"] = summary_result["customer_based_orders"]
        merged_result["item_based_summary"] = summary_result["item_based_summary"]
        merged_result["table_summary"] = summary_result["table_summary"]
        
        # 추출한 상품 정보를 결과에 포함
        if final_product_list_for_llm:
            available_products = []
            for product_name in final_product_list_for_llm:
                available_products.append({
                    "name": product_name,
                    "category": "",
                    "price": "",
                    "delivery_date": "",
                    "deadline": ""
                })
            merged_result["available_products"] = available_products
        
        # 10단계: 메인 분석 바탕으로 주문자별 정보 등 기타 정보 생성 완료 (100%)
        progress_logger.add_log(
            ProgressPhase.FINAL_PROCESSING_COMPLETE,
            [
                f"추출된 상품: {len(merged_result.get('available_products', []))}개",
                f"시간 기반 주문: {len(merged_result.get('time_based_orders', []))}개",
                f"고객 기반 주문: {len(merged_result.get('customer_based_orders', []))}개",
                f"품목별 요약: {len(merged_result.get('item_based_summary', []))}개"
            ]
        )
        
        # 진행상태 로그를 결과에 포함
        merged_result["progress_logs"] = progress_logger.get_logs()
        
        return merged_result
        
    except Exception as e:
        return {
            "error": True,
            "message": f"분석 중 예상치 못한 오류가 발생했습니다: {str(e)}",
            "progress_logs": progress_logger.get_logs()
        }

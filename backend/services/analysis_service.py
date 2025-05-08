import json
import re
import concurrent.futures
from typing import List, Dict, Any, Optional
from datetime import datetime
import traceback

from utils.text_processing import (
    filter_conversation_by_date,
    split_conversation_into_chunks,
    is_valid_item_name
)
from utils.validation import (
    is_valid_order_format,
    validate_analysis_result,
    filter_invalid_items
)
from services.llm_service import analyze_conversation_chunk

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
        result = analyze_conversation_with_llm(conversation_text, shop_name)
        
        # 결과 검증 및 보정
        result = validate_analysis_result(result)
        
        # 잘못된 품목 필터링
        if "time_based_orders" in result:
            result["time_based_orders"] = filter_invalid_items(result["time_based_orders"])
            
        if "item_based_summary" in result:
            result["item_based_summary"] = filter_invalid_items(result["item_based_summary"])
            
        if "customer_based_orders" in result:
            result["customer_based_orders"] = filter_invalid_items(result["customer_based_orders"])
            
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

def analyze_conversation_with_llm(conversation_text: str, shop_name: Optional[str] = None) -> Dict[str, Any]:
    """
    LLM을 이용하여 대화를 분석합니다. 긴 대화는 청크로 나누어 병렬 처리합니다.
    
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
        
        # 분할 결과 병합
        return merge_chunk_results(chunk_results)
    else:
        # 단일 청크로 처리
        return analyze_conversation_chunk(conversation_text, shop_name)

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

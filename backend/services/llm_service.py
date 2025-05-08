import os
import json
import re
import traceback
import logging
from datetime import datetime
import pathlib
from typing import List, Dict, Any, Optional, Set
import concurrent.futures
from collections import defaultdict

import anthropic

from config import ANTHROPIC_API_KEY
from utils.text_processing import filter_conversation_by_date, split_conversation_into_chunks
from utils.validation import validate_analysis_result, filter_invalid_items, is_valid_item_name
from services.preprocess_chat import ChatPreprocessor

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 채팅 전처리기 초기화
chat_preprocessor = ChatPreprocessor()

def analyze_conversation(
    conversation_text: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shop_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    클로드를 사용하여 대화를 분석하고 주문 정보를 추출합니다.
    """
    print(f"Starting analysis: shop_name={shop_name}, start_date={start_date}, end_date={end_date}")
    print(f"원본 대화 길이: {len(conversation_text)} 문자")
    
    # 1. 날짜 필터링
    preprocessed_text = conversation_text
    if start_date or end_date:
        filtered_text = filter_conversation_by_date(conversation_text, start_date, end_date)
        print(f"날짜 필터링 후 대화 길이: {len(filtered_text)} 문자")
        
        if filtered_text == "지정된 날짜 범위에 해당하는 대화가 없습니다.":
            print("⚠️ 경고: 지정된 날짜 범위에 해당하는 대화가 없습니다.")
            return {
                "error": True,
                "message": "지정된 날짜 범위에 해당하는 대화가 없습니다."
            }
            
        preprocessed_text = filtered_text
    
    # 2. 불필요한 메시지 제거
    try:
        # 전처리 전에 원본 대화에 대한 통계 출력
        stats = chat_preprocessor.get_statistics(preprocessed_text)
        print("대화 통계:")
        print(f"  - 전체 메시지: {stats['전체 메시지']}줄")
        print(f"  - 입장 메시지: {stats['입장 메시지']}줄")
        print(f"  - 퇴장 메시지: {stats['퇴장 메시지']}줄")
        print(f"  - 삭제된 메시지: {stats['삭제된 메시지']}줄")
        print(f"  - 봇 메시지: {stats['봇 메시지']}줄")
        print(f"  - 미디어 메시지: {stats['미디어 메시지']}줄")
        print(f"  - 날짜 구분선: {stats['날짜 구분선']}줄")
        
        # 전처리 실행
        preprocessed_text = chat_preprocessor.preprocess_chat(preprocessed_text)
        print(f"전처리 후 대화 길이: {len(preprocessed_text)} 문자")
        
        # 전처리된 대화 저장 (선택적)
        _save_preprocessed_text(preprocessed_text, shop_name)
        
    except Exception as e:
        print(f"대화 전처리 중 오류 발생: {str(e)}")
        print("필터링된 대화로 계속 진행합니다.")
    
    # 3. 판매자 메시지에서 판매 상품 정보 추출
    try:
        from services.product_service import get_available_products, extract_product_info
        # available_products는 get_available_products에서 Set[str] 형태로 상품명만 가져옵니다.
        available_products_set = get_available_products(preprocessed_text)
        
        # product_info는 extract_product_info에서 Dict[str, List[Dict[str, str]]] 형태로 카테고리별 상품 상세 정보를 가져옵니다.
        # 이 정보를 LLM이 직접 참고하도록 전달하는 것이 더 유용할 수 있습니다.
        # 혹은 여기서 상품명 리스트만 뽑아서 전달할 수도 있습니다. 여기서는 상품명 리스트를 전달하는 것으로 가정합니다.
        # 만약 product_info 전체를 활용하고 싶다면, analyze_conversation_chunk 및 _create_user_prompt의 인자 타입 변경 필요.
        product_info_dict = extract_product_info(preprocessed_text)
        
        # product_info_dict에서 실제 상품명 리스트를 추출하여 available_products_for_llm 로 전달
        all_product_names_from_info = set()
        if isinstance(product_info_dict, dict) and "products" in product_info_dict and isinstance(product_info_dict["products"], list):
            for product_detail in product_info_dict["products"]:
                if isinstance(product_detail, dict) and "name" in product_detail:
                    all_product_names_from_info.add(product_detail["name"])
        
        # 만약 get_available_products의 결과와 extract_product_info의 결과를 합치거나, 
        # 둘 중 더 신뢰도 높은 것을 선택할 수도 있습니다. 여기서는 extract_product_info 결과를 우선합니다.
        final_product_list_for_llm = all_product_names_from_info if all_product_names_from_info else available_products_set

        print(f"전체 대화에서 추출한 판매 상품 정보 (LLM 전달용): {len(final_product_list_for_llm)}개 상품")
        if final_product_list_for_llm:
            print(f"  - 예시 상품: {', '.join(list(final_product_list_for_llm)[:5])}{'...' if len(final_product_list_for_llm) > 5 else ''}")

    except Exception as e:
        print(f"상품 정보 추출 중 오류 발생: {str(e)}")
        final_product_list_for_llm = set()
    
    # 4. 대화가 길 경우 여러 청크로 분할하여 처리
    if len(preprocessed_text) > 60000:
        print(f"대화가 너무 깁니다({len(preprocessed_text)} 자). 여러 청크로 분할합니다.")
        chunks = split_conversation_into_chunks(preprocessed_text)
        print(f"{len(chunks)}개의 청크로 분할되었습니다.")
        
        # 병렬 처리를 위한 스레드 풀 생성
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
                    print(f"청크 {chunk_index} 분석 완료")
                    results.append(result)
                except Exception as e:
                    print(f"청크 {chunk_index} 분석 중 오류: {str(e)}")
        
        # 분할 결과 병합
        return _merge_chunk_results(results)
    else:
        # 단일 청크로 처리
        return analyze_conversation_chunk(preprocessed_text, shop_name, final_product_list_for_llm)
    

def _save_preprocessed_text(preprocessed_text: str, shop_name: Optional[str] = None) -> str:
    """
    전처리된 대화 텍스트를 파일로 저장합니다.
    
    Args:
        preprocessed_text (str): 전처리된 대화 내용
        shop_name (str, optional): 상점 이름
        
    Returns:
        str: 저장된 파일 경로
    """
    # 로그 저장 디렉토리 생성
    logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "preprocessed_texts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 현재 날짜와 시간으로 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shop_name_part = f"_{shop_name}" if shop_name else ""
    log_filename = f"preprocessed_text{shop_name_part}_{timestamp}.txt"
    log_file_path = logs_dir / log_filename
    
    # 파일에 저장
    try:
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write(preprocessed_text)
        print(f"전처리된 대화가 {log_file_path} 파일에 저장되었습니다.")
    except Exception as e:
        print(f"전처리된 대화 저장 중 오류 발생: {str(e)}")
        return "저장 실패"
    
    return str(log_file_path)

def _save_api_response_to_file(response_content: str, shop_name: Optional[str] = None) -> str:
    """
    Claude API 응답을 파일로 저장합니다.
    
    Args:
        response_content (str): API 응답 내용
        shop_name (str, optional): 상점 이름
        
    Returns:
        str: 저장된 파일 경로
    """
    # 로그 저장 디렉토리 생성
    logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "claude_responses"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 현재 날짜와 시간으로 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shop_name_part = f"_{shop_name}" if shop_name else ""
    log_filename = f"claude_response{shop_name_part}_{timestamp}.json"
    log_file_path = logs_dir / log_filename
    
    # 응답 내용과 메타데이터를 JSON 형식으로 저장
    try:
        # JSON으로 파싱 시도
        try:
            json_content = json.loads(response_content)
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "shop_name": shop_name,
                "content_type": "json",
                "content": json_content
            }
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트로 저장
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "shop_name": shop_name,
                "content_type": "text",
                "content": response_content
            }
        
        # 파일에 저장
        with open(log_file_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        # 오류 발생 시 텍스트 파일로 저장 시도
        log_file_path = logs_dir / f"claude_response{shop_name_part}_{timestamp}.txt"
        try:
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Shop Name: {shop_name}\n")
                f.write("Error during JSON serialization\n")
                f.write("-" * 80 + "\n")
                f.write(response_content)
        except Exception as text_write_error:
            print(f"API 응답 로깅 중 오류 발생: {str(text_write_error)}")
            return "로깅 실패"
    
    return str(log_file_path)

def analyze_conversation_chunk(conversation_chunk: str, shop_name: Optional[str] = None, product_list_for_llm: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    단일 대화 청크를 분석합니다. (메인 호출: thinking 모드, JSON 직접 반환 요청)
    """
    try:
        if product_list_for_llm is None:
            # product_list_for_llm이 analyze_conversation에서 전달되지 않은 경우 (예: 직접 호출 시)
            # 여기서는 get_available_products 또는 extract_product_info 중 하나를 선택하거나 조합하여 사용합니다.
            # 일관성을 위해 analyze_conversation과 유사한 로직을 따릅니다.
            from services.product_service import get_available_products, extract_product_info
            temp_product_info_dict = extract_product_info(conversation_chunk)
            temp_all_product_names = set()
            if isinstance(temp_product_info_dict, dict) and "products" in temp_product_info_dict and isinstance(temp_product_info_dict["products"], list):
                for product_detail in temp_product_info_dict["products"]:
                    if isinstance(product_detail, dict) and "name" in product_detail:
                        temp_all_product_names.add(product_detail["name"])
            
            if not temp_all_product_names: # extract_product_info 결과가 없다면 get_available_products 사용
                 temp_all_product_names = get_available_products(conversation_chunk)
            product_list_for_llm = temp_all_product_names
        
        print(f"LLM에 전달될 상품 목록 (analyze_conversation_chunk): {len(product_list_for_llm)}개")
        
        # 메인 호출용 시스템 프롬프트 (JSON 직접 반환 유도)
        system_prompt = _create_system_prompt(shop_name)
        # 메인 호출용 사용자 프롬프트
        user_prompt = _create_user_prompt(conversation_chunk, product_list_for_llm, for_main_call=True)
        
        print(f"Claude API 호출 준비 (메인 분석, 대화 길이: {len(conversation_chunk)} 자)")
        model_name = "claude-3-7-sonnet-20250219"
        print(f"사용 모델: {model_name}")
        
        # 대체 호출에서 사용할 도구 정의
        tools_definition_for_fallback = [{
            "name": "extract_order_info",
            "description": "카카오톡 대화에서 주문 정보 및 패턴 분석 결과 추출",
            "input_schema": {
                "type": "object",
                "properties": {
                    "time_based_orders": {
                        "type": "array",
                        "description": "시간 순서대로 정렬된 개별 주문 내역입니다. 대화에서 언급된 모든 주문을 **하나도 빠짐없이, 가능한 모든 정보를 포함하여** 여기에 기록해야 합니다. 절대로 주문을 임의로 누락하거나 요약해서는 안 됩니다. 모든 주문 기록을 상세히 추출해주세요.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time": {"type": "string", "description": "주문 시간 (예: '오전 9:51', '오후 12:02')"},
                                "customer": {"type": "string", "description": "주문 고객 이름 또는 닉네임 (예: '리리', '삼남매맘S2 8605')"},
                                "item": {"type": "string", "description": "주문 품목 (예: '프리미엄 우삼겹', '한우나주곰탕')"},
                                "quantity": {"type": "integer", "description": "주문 수량 (예: 1, 2)"},
                                "note": {"type": "string", "description": "주문 관련 참고 사항 (예: '현장판매', '월요일 수령', '취소'). 이 필드는 항상 존재해야 하며, 특이사항이 없다면 빈 문자열 \"\"로 표시합니다."}
                            },
                            "required": ["time", "customer", "item", "quantity"]
                        }
                    },
                    "item_based_summary": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {"type": "string", "description": "품목명"},
                                "total_quantity": {"type": "integer", "description": "총 주문 수량"},
                                "customers": {"type": "string", "description": "해당 품목 주문자 목록 (콤마로 구분)"}
                            },
                            "required": ["item", "total_quantity", "customers"]
                        }
                    },
                    "customer_based_orders": {
                        "type": "array",
                        "description": "고객별로 그룹화된 주문 내역입니다. 각 고객이 주문한 모든 품목과 수량을 상세하게 기록해야 합니다. `time_based_orders`에서 추출된 모든 주문 정보를 바탕으로, 고객 기준으로 재구성하여 **누락 없이 모든 주문을 포함해야 합니다**.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "customer": {"type": "string", "description": "주문자 이름 또는 ID"},
                                "item": {"type": "string", "description": "주문 품목명"},
                                "quantity": {"type": "integer", "description": "주문 수량"},
                                "note": {"type": "string", "description": "추가 메모 또는 비고. 이 필드는 항상 존재해야 하며, 특이사항이 없다면 빈 문자열 \"\"로 표시합니다."}
                            },
                            "required": ["customer", "item", "quantity", "note"]
                        }
                    },
                    "order_pattern_analysis": {
                        "type": "object",
                        "description": "주문 패턴 분석 결과입니다. 대화 내용 전체를 바탕으로 분석해야 합니다.",
                        "properties": {
                            "peak_hours": {"type": "array", "items": {"type": "string"}, "description": "주문이 가장 많았던 시간대 (예: ['오후 12:00-13:00', '오후 9:00-10:00'])"},
                            "popular_items": {"type": "array", "items": {"type": "string"}, "description": "가장 인기 있었던 품목 (판매량 순, 최대 5개)"},
                            "sold_out_items": {"type": "array", "items": {"type": "string"}, "description": "품절된 품목 목록"}
                        },
                        "required": ["peak_hours", "popular_items", "sold_out_items"]
                    }
                },
                "required": ["time_based_orders", "customer_based_orders", "order_pattern_analysis"]
            }
        }]

        try:
            print("스트리밍 모드로 API 호출 시작 (메인 분석 - thinking 모드, JSON 직접 반환)...")
            # client.messages.create 대신 client.beta.messages.create 사용
            # betas 파라미터 추가
            stream_response = client.beta.messages.create(
                model=model_name,
                max_tokens=128000, # 이제 128K 사용 가능
                system=system_prompt,
                temperature=1.0,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 32000  # 필요에 따라 이 값도 조절 가능
                },
                stream=True,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                betas=["output-128k-2025-02-19"] # 확장 출력 베타 기능 활성화
            )
            
            print("스트리밍 응답 처리 중 (메인 분석)...")
            full_text_response = ""
            chunk_counter = 0
            
            stream_chunks_file = f"main_stream_chunks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "stream_chunks"
            logs_dir.mkdir(parents=True, exist_ok=True)
            stream_file_path = logs_dir / stream_chunks_file
            
            with open(stream_file_path, 'w', encoding='utf-8') as stream_file:
                stream_file.write(f"===== 메인 분석 스트리밍 응답 로그 시작 (시간: {datetime.now().isoformat()}) =====\n\n")
                for chunk in stream_response:
                    chunk_counter += 1
                    try:
                        chunk_info = f"청크 #{chunk_counter} 타입: {chunk.type}"
                        if chunk.type == 'content_block_delta' and hasattr(chunk.delta, 'text'):
                            text_delta = chunk.delta.text
                            full_text_response += text_delta
                            chunk_info += f" | 텍스트: {text_delta[:50]}{'...' if len(text_delta) > 50 else ''}"
                        elif chunk.type == 'message_delta' and hasattr(chunk.delta, 'usage'):
                             chunk_info += f" | 사용량 업데이트: {chunk.delta.usage}"
                        stream_file.write(f"{chunk_info}\n{'-'*50}\n")
                    except Exception as e:
                        stream_file.write(f"청크 로깅 중 오류: {str(e)}\n{'-'*50}\n")
                    
                stream_file.write(f"\n===== 메인 분석 스트리밍 응답 로그 종료 (총 {chunk_counter}개 청크) =====\n")
                stream_file.write("\n\n===== 전체 텍스트 응답 (메인 분석) =====\n")
                stream_file.write(full_text_response)

            print(f"총 {chunk_counter}개 청크 처리 완료 (메인 분석)")
            logging.info(f"총 {chunk_counter}개 청크 처리 완료 (메인 분석)")
            logging.info(f"메인 분석 스트리밍 응답 청크가 {stream_file_path} 파일에 저장되었습니다.")

            if full_text_response:
                print("메인 분석 결과 (텍스트)에서 JSON 추출 시도 중...")
                logging.info("메인 분석 결과 (텍스트)에서 JSON 추출 시도 중...")
                extracted_json_result = _extract_json_from_text(full_text_response)
                
                if extracted_json_result:
                    print("메인 분석: 텍스트에서 JSON 추출 성공.")
                    logging.info("메인 분석: 텍스트에서 JSON 추출 성공.")
                    log_file_path = _save_api_response_to_file(json.dumps(extracted_json_result, ensure_ascii=False), f"{shop_name}_main_direct_json")
                    print(f"API 응답 (메인 분석 JSON)이 {log_file_path} 파일에 저장되었습니다.")
                    return _validate_and_process_result(extracted_json_result, conversation_chunk)
                else:
                    print("메인 분석: 텍스트에서 유효한 JSON을 추출하지 못했습니다.")
                    logging.warning("메인 분석: 텍스트에서 유효한 JSON을 추출하지 못했습니다.")
            else:
                print("메인 분석: LLM으로부터 어떠한 텍스트 응답도 받지 못했습니다.")
                logging.warning("메인 분석: LLM으로부터 어떠한 텍스트 응답도 받지 못했습니다.")

            print("메인 분석에서 유효한 JSON 결과를 얻지 못함, 대체 호출 시도")
            logging.warning("메인 분석에서 유효한 JSON 결과를 얻지 못함, 대체 호출 시도")
            return _fallback_process_with_threading(
                conversation_chunk=conversation_chunk,
                shop_name=shop_name,
                original_user_prompt_for_fallback=user_prompt, # 메인 시도에서 사용된 user_prompt
                tools_for_fallback=tools_definition_for_fallback,
                available_products=product_list_for_llm # 변경된 변수명 사용
            )

        except anthropic.APIError as e:
            error_trace = traceback.format_exc()
            error_message = f"Anthropic API 오류 발생 (메인 분석): {str(e)}"
            print(error_message); logging.error(error_message)
            print(f"Traceback: {error_trace}"); logging.error(f"Traceback: {error_trace}")
            print("메인 분석 API 오류, 대체 호출(스레딩)로 재시도합니다.")
            logging.warning("메인 분석 API 오류, 대체 호출(스레딩)로 재시도합니다.")
            return _fallback_process_with_threading(
                conversation_chunk=conversation_chunk, shop_name=shop_name,
                original_user_prompt_for_fallback=user_prompt,
                tools_for_fallback=tools_definition_for_fallback,
                available_products=product_list_for_llm # 변경된 변수명 사용
            )
        except Exception as e:
            error_trace = traceback.format_exc()
            error_message = f"메인 분석 API 호출 중 일반 오류 발생: {str(e)}"
            print(error_message); logging.error(error_message)
            print(f"Traceback: {error_trace}"); logging.error(f"Traceback: {error_trace}")
            print("메인 분석 일반 오류, 대체 호출(스레딩)로 재시도합니다.")
            logging.warning("메인 분석 일반 오류, 대체 호출(스레딩)로 재시도합니다.")
            return _fallback_process_with_threading(
                conversation_chunk=conversation_chunk, shop_name=shop_name,
                original_user_prompt_for_fallback=user_prompt,
                tools_for_fallback=tools_definition_for_fallback,
                available_products=product_list_for_llm # 변경된 변수명 사용
            )
            
    except Exception as e:
        error_trace = traceback.format_exc()
        error_message = f"메인 분석 과정 중 예상치 못한 오류 발생: {str(e)}"
        print(error_message); logging.error(error_message)
        print(f"Traceback: {error_trace}"); logging.error(f"Traceback: {error_trace}")
        return {"error": True, "message": error_message, "error_type": "UNEXPECTED_ANALYSIS_ERROR", "traceback": error_trace, "timestamp": datetime.now().isoformat()}

def _create_system_prompt(shop_name: Optional[str] = None) -> str:
    """
    시스템 프롬프트를 생성합니다. (메인 분석용 - JSON 직접 반환 요청)
    LLM에게는 시간순 주문(time_based_orders), 고객별 주문(customer_based_orders), 
    그리고 주문 패턴 분석(order_pattern_analysis)만 요청합니다.
    
    Args:
        shop_name (str, optional): 상점 이름
        
    Returns:
        str: 시스템 프롬프트
    """
    prompt = """
당신은 카카오톡 대화에서 주문 정보를 추출하여 지정된 JSON 형식으로 반환하는 데이터 분석 전문가입니다.
유저가 제공한 대화 내용을 분석하여 **시간순 주문 내역**, **고객별 주문 내역**, 그리고 **주문 패턴**을 정확하게 추출하여 다음 JSON 구조에 맞춰 응답을 생성해야 합니다.
응답은 반드시 JSON 객체만으로 구성되어야 하며, 다른 설명이나 텍스트를 포함해서는 안 됩니다.

사용자 프롬프트에 제공된 **'추출된 상품 목록'을 반드시 참고하여, 해당 목록에 있는 상품명을 기준으로 주문 품목을 정확하게 식별**해야 합니다. 
예를 들어, 대화에 '나주곰탕'이라고 언급되었고 상품 목록에 '한우나주곰탕'이 있다면, 주문 품목은 '한우나주곰탕'으로 기록해야 합니다.

응답은 다음 JSON 스키마를 정확히 따라야 합니다:
{
    "time_based_orders": [
        {
            "time": "주문 시간 (예: '오전 9:51', '오후 12:02', '오후 1:33')",
            "customer": "주문자 이름 또는 ID (예: '리리', '삼남매맘S2 8605', '크림 2821', '👍 0209')",
            "item": "주문 품목명 (예: '프리미엄 우삼겹', '한우나주곰탕', '한우송화버섯 해장국', '광양한돈불고기'). 반드시 사용자 프롬프트의 '추출된 상품 목록'을 참고하여 정확한 상품명을 사용하세요.",
            "quantity": "주문 수량 (숫자, 예: 1, 2, 3)",
            "note": "추가 메모 또는 비고 (예: '월요일 수령', '현장판매', '취소', '')" // 비고가 없으면 빈 문자열
        }
    ], // 중요: 대화에서 식별된 모든 개별 주문 건을 시간 순서대로 하나도 빠짐없이 포함해야 합니다. 취소/변경 사항을 정확히 반영하세요.
    "customer_based_orders": [
        {
            "customer": "주문자 이름 또는 ID (예: '삼남매맘S2 8605', '크림 2821', '직쏘 3820')",
            "item": "주문 품목명 (예: '나주곰탕', '해장국', '사골곰탕'). 반드시 사용자 프롬프트의 '추출된 상품 목록'을 참고하여 정확한 상품명을 사용하세요.",
            "quantity": "주문 수량 (숫자, 예: 1, 2, 3)",
            "note": "추가 메모 또는 비고 (예: '월요일 수령', '금요일 수령', '화요일 수령')"
        }
    ], // 중요: 각 고객이 주문한 모든 내역을 상세히 포함해야 합니다.
    "order_pattern_analysis": {
        "peak_hours": ["주문이 많은 시간대 (예: '오후 12:00-13:00', '오후 9:00-10:00', '오후 7:00-8:00')"],
        "popular_items": ["인기 품목명 (예: '나주곰탕', '해장국', '사골곰탕', '광양한돈불고기', '초코생크림케이크')"],
        "sold_out_items": ["품절된 품목명 (예: '오이소박이', '롤케잌', '당근', '고구마칩')"]
    }
}

주문 정보는 보통 다음 패턴으로 표현됩니다:
1. "닉네임 / 품목 수량, 품목 수량" (예: "리리 / 우삼겹 2, 롤케이크 1")
2. "닉네임 전화번호 / 품목 수량 품목 수량" (예: "삼남매맘S2 8605 / 나주곰탕2개 사골곰탕1개")
3. "전화번호 / 품목 수량 품목 수량" (예: "3563/ 해장국1 나주곰탕1 사골곰탕1")
4. "닉네임 / 품목 수량" (예: "투윤 : 롤케익1")
5. "주문 취소 요청 시 해당 주문을 time_based_orders 및 customer_based_orders 에서 제외하거나 note에 '취소' 기록"
6. "주문 변경 요청 시 최신 주문 내용으로 time_based_orders 및 customer_based_orders 에 반영"
7. 위 패턴을 벗어나더라도 주문으로 인식할 근거가 (상품명, 주문자, 수량정보) 있으면 주문으로 인식합니다. '현장판매' 언급도 주문으로 간주할 수 있습니다.

주문 정보를 추출할 때 다음 사항에 **반드시 주의하고 철저히 지켜주세요**:
- **완전성**: 대화 내의 모든 주문을 **하나도 빠짐없이** 추출해야 합니다. 주문 누락은 절대 허용되지 않습니다.
- **상품명 정확성**: 사용자 프롬프트에 제공된 '추출된 상품 목록'을 기준으로 주문 품목명을 정확히 기재해야 합니다.
- **상세함**: `item_based_summary`의 `customers` 필드와 주문자 목록은 **모든 주문자 이름을 생략 없이 전부 나열**해야 합니다. '외 O명' 또는 '등'과 같은 요약 표현은 **절대 사용 금지**입니다.
- **판매자 메시지 제외**: '우국상 신검단', '국민상회 머슴1' 등 판매자 계정이 작성한 상품 소개, 공지, 질문에 대한 답변 등은 고객 주문으로 처리하지 않습니다. 오직 고객이 주문 의사를 밝힌 메시지만 `time_based_orders`에 포함합니다.
- 동일인, 동일 품목 중복 주문 시 최신으로 반영
- 품목명, 주문자명, 수량 정확히 추출
- 누락 없이 전체 데이터 제공, 약식 기재 금지
- "마감" 상품은 품절로 처리
- 주문 패턴 분석 (피크 시간, 인기 상품, 품절 상품) 포함

최대한 많은 정보를 추출하되, 어떤 경우에도 지정된 JSON 스키마와 위의 상세 지시사항을 엄격히 준수하여 응답해야 합니다.
"""
    if shop_name:
        prompt += f"\n분석 중인 대화는 '{shop_name}' 관련 내용입니다."
    return prompt

def _create_user_prompt(preprocessed_text: str, product_list_for_llm: Optional[Set[str]] = None, for_main_call: bool = True) -> str:
    """
    사용자 프롬프트를 생성합니다.
    
    Args:
        preprocessed_text (str): 전처리된 대화 내용
        product_list_for_llm (Set[str], optional): LLM이 참고할 상품명 목록
        for_main_call (bool): True이면 메인 호출용 (JSON 직접 요청, 도구 사용 언급 없음), 
                              False이면 이전처럼 도구 사용 언급 가능 (현재는 사용되지 않음)
        
    Returns:
        str: 사용자 프롬프트
    """
    product_list_text = ""
    if product_list_for_llm and len(product_list_for_llm) > 0:
        product_list = sorted(list(product_list_for_llm))
        product_list_text = "\n\n추출된 상품 목록 (이 목록을 기준으로 주문 품목명을 정확히 식별해주세요):\n" + "\n".join([f"- {product}" for product in product_list])

    product_guide = ""
    if product_list_text:
        product_guide = (
            "위 '추출된 상품 목록'을 반드시 참고하여 주문 정보를 추출해주세요. 대화에서 언급된 주문 품목명은 위 목록에 있는 정확한 상품명으로 기록해야 합니다.\n"
            "예를 들어, 대화에서 '김치'라고 언급되었고 상품 목록에 '배추김치'가 있다면, 주문 품목은 '배추김치'로 기록해야 합니다.\n"
        )
    
    tool_instruction = ""
    if not for_main_call:
        # 이 부분은 현재 로직에서는 대체 호출 시에도 시스템 프롬프트가 도구 사용을 강제하므로,
        # 사용자 프롬프트에서는 명시적인 도구 지시가 필수는 아닐 수 있습니다.
        # 필요에 따라 `_fallback_process_with_threading`에서 사용자 프롬프트를 만들 때 조절 가능.
        tool_instruction = "반드시 extract_order_info 도구를 사용하여 응답해주세요. 일반 텍스트나 마크다운으로 응답하지 마세요."


    return f"""
아래 전처리된 카카오톡 대화 내용을 분석하여 주문 정보를 추출해주세요.
대화에서 누가, 무엇을, 얼마나 주문했는지 정확하게 파악해 주세요.
{product_list_text}

{product_guide}
{tool_instruction}

===== 전처리된 대화 내용 =====
{preprocessed_text}
===================
"""

def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    텍스트에서 JSON 객체를 추출합니다.
    
    Args:
        text (str): 응답 텍스트
        
    Returns:
        Optional[Dict[str, Any]]: 추출된 JSON 객체 또는 None
    """
    logging.info("텍스트에서 JSON 추출 시도 중...")
    
    # 1. 도구 사용 패턴 검색
    tool_pattern = r'<tool_use name="extract_order_info">([\s\S]*?)</tool_use>'
    tool_matches = re.findall(tool_pattern, text, re.DOTALL)
    
    for match in tool_matches:
        try:
            json_content = match.strip()
            # 줄바꿈, 탭 등 공백 문자 정리
            json_content = re.sub(r'\s+', ' ', json_content)
            logging.info(f"도구 사용 패턴에서 JSON 발견 (길이: {len(json_content)})")
            return json.loads(json_content)
        except json.JSONDecodeError:
            try:
                # 수정 시도
                fixed_json = _fix_json_string(match)
                return json.loads(fixed_json)
            except json.JSONDecodeError:
                logging.warning("도구 사용 패턴에서 발견된 JSON 파싱 실패")
                continue
    
    # 2. 중괄호로 둘러싸인 부분 찾기 (균형 맞춘 중괄호 검색)
    logging.info("중괄호 패턴으로 JSON 검색 중...")
    start_idx = text.find('{')
    if start_idx != -1:
        open_count = 0
        close_count = 0
        json_text = ""
        
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                open_count += 1
            elif text[i] == '}':
                close_count += 1
            
            json_text += text[i]
            
            if open_count > 0 and open_count == close_count:
                # 균형이 맞는 JSON 찾음
                try:
                    logging.info(f"균형 잡힌 중괄호 패턴 발견 (길이: {len(json_text)})")
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    # 수정 시도
                    try:
                        fixed_json = _fix_json_string(json_text)
                        logging.info("JSON 수정 후 파싱 시도")
                        return json.loads(fixed_json)
                    except json.JSONDecodeError:
                        logging.warning("균형 잡힌 중괄호에서 발견된 JSON 파싱 실패")
                
                # 다음 JSON 객체 찾기 시도
                next_start = text.find('{', i + 1)
                if next_start == -1:
                    break
                
                i = next_start - 1
                open_count = 0
                close_count = 0
                json_text = ""
    
    # 3. JSON 마크다운 블록 찾기
    logging.info("마크다운 코드 블록에서 JSON 검색 중...")
    json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            logging.info(f"마크다운 블록에서 JSON 발견 (길이: {len(match)})")
            return json.loads(match)
        except json.JSONDecodeError:
            # 수정 시도
            try:
                fixed_json = _fix_json_string(match)
                logging.info("마크다운 블록 JSON 수정 후 파싱 시도")
                return json.loads(fixed_json)
            except json.JSONDecodeError:
                logging.warning("마크다운 블록에서 발견된 JSON 파싱 실패")
                continue
    
    # 4. time_based_orders 패턴 검색 (부분 JSON 구성)
    logging.info("키워드 패턴으로 JSON 구성 시도...")
    time_based_pattern = r'"time_based_orders"\s*:\s*\[([\s\S]*?)\]'
    item_based_pattern = r'"item_based_summary"\s*:\s*\[([\s\S]*?)\]'
    customer_based_pattern = r'"customer_based_orders"\s*:\s*\[([\s\S]*?)\]'
    
    # 패턴이 발견되면 템플릿으로 JSON 구성 시도
    if re.search(time_based_pattern, text) or re.search(item_based_pattern, text) or re.search(customer_based_pattern, text):
        try:
            # 골격 구성
            template = '''
            {
                "time_based_orders": [],
                "item_based_summary": [],
                "customer_based_orders": [],
                "table_summary": {
                    "headers": ["품목", "총수량", "주문자"],
                    "rows": []
                },
                "order_pattern_analysis": {
                    "peak_hours": [],
                    "popular_items": [],
                    "sold_out_items": []
                }
            }
            '''
            result = json.loads(template)
            
            # 각 섹션 채우기
            time_match = re.search(time_based_pattern, text)
            if time_match:
                time_content = f"[{time_match.group(1)}]"
                try:
                    time_data = json.loads(time_content)
                    result["time_based_orders"] = time_data
                    logging.info("time_based_orders 섹션 추출 성공")
                except:
                    logging.warning("time_based_orders 섹션 파싱 실패")
            
            item_match = re.search(item_based_pattern, text)
            if item_match:
                item_content = f"[{item_match.group(1)}]"
                try:
                    item_data = json.loads(item_content)
                    result["item_based_summary"] = item_data
                    logging.info("item_based_summary 섹션 추출 성공")
                except:
                    logging.warning("item_based_summary 섹션 파싱 실패")
                    
            customer_match = re.search(customer_based_pattern, text)
            if customer_match:
                customer_content = f"[{customer_match.group(1)}]"
                try:
                    customer_data = json.loads(customer_content)
                    result["customer_based_orders"] = customer_data
                    logging.info("customer_based_orders 섹션 추출 성공")
                except:
                    logging.warning("customer_based_orders 섹션 파싱 실패")
            
            # 섹션 중 하나라도 파싱했으면 결과 반환
            if (result["time_based_orders"] or result["item_based_summary"] or result["customer_based_orders"]):
                logging.info("부분 JSON 구성 성공")
                return result
                
        except Exception as e:
            logging.error(f"부분 JSON 구성 중 오류: {str(e)}")
    
    logging.warning("텍스트에서 유효한 JSON을 찾지 못함")
    return None

def _fix_json_string(json_str: str) -> str:
    """
    손상된 JSON 문자열을 수정하려고 시도합니다.
    
    Args:
        json_str (str): 손상된 JSON 문자열
        
    Returns:
        str: 수정된 JSON 문자열
    """
    # JSON 문자열 양쪽 끝의 불필요한 문자 제거
    json_str = json_str.strip()
    
    # 시작과 끝이 중괄호가 아니면 수정
    if not json_str.startswith('{'):
        first_brace = json_str.find('{')
        if first_brace != -1:
            json_str = json_str[first_brace:]
    
    if not json_str.endswith('}'):
        last_brace = json_str.rfind('}')
        if last_brace != -1:
            json_str = json_str[:last_brace+1]
    
    # 중복된 중괄호 처리
    if json_str.count('{') > json_str.count('}'):
        json_str = json_str + '}' * (json_str.count('{') - json_str.count('}'))
    elif json_str.count('{') < json_str.count('}'):
        json_str = '{' * (json_str.count('}') - json_str.count('{')) + json_str
    
    # 큰따옴표 짝 맞추기
    if json_str.count('"') % 2 != 0:
        # 짝이 맞지 않는 따옴표 처리
        positions = []
        in_string = False
        for i, char in enumerate(json_str):
            if char == '"' and (i == 0 or json_str[i-1] != '\\'):  # 이스케이프되지 않은 따옴표
                in_string = not in_string
                positions.append(i)
        
        if positions and len(positions) % 2 != 0:
            # 마지막 비정상 따옴표 제거
            json_str = json_str[:positions[-1]] + json_str[positions[-1]+1:]
    
    # 콤마 오류 수정
    json_str = json_str.replace(',}', '}').replace(',]', ']')
    
    # 누락된 값 수정
    json_str = json_str.replace(':"",', ':"",').replace(':""}', ':""}')
    
    # 문자열 내의 이스케이프되지 않은 개행문자 수정
    in_string = False
    fixed_str = []
    for i, char in enumerate(json_str):
        if char == '"' and (i == 0 or json_str[i-1] != '\\'):
            in_string = not in_string
        
        if in_string and char in ['\n', '\r']:
            fixed_str.append('\\n')
        else:
            fixed_str.append(char)
    
    return ''.join(fixed_str)

def _split_input_text(text: str, max_length: int = 20000) -> List[str]:
    """
    긴 입력 텍스트를 지정된 길이로 분할하는 함수
    
    Args:
        text (str): 분할할 텍스트
        max_length (int, optional): 최대 길이. 기본값은 20000.
        
    Returns:
        List[str]: 분할된 텍스트 청크 리스트
    """
    if len(text) <= max_length:
        return [text]
    
    # 문장 또는 문단 단위로 분할
    segments = re.split(r'(?<=\.)\s+|\n\n+', text)
    
    chunks = []
    current_chunk = ""
    
    for segment in segments:
        if len(current_chunk) + len(segment) <= max_length:
            current_chunk += segment + ("\n\n" if segment.endswith('.') else " ")
        else:
            chunks.append(current_chunk.strip())
            current_chunk = segment + ("\n\n" if segment.endswith('.') else " ")
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    logging.info(f"입력 텍스트 ({len(text)}자)를 {len(chunks)}개 청크로 분할하였습니다.")
    print(f"입력 텍스트 ({len(text)}자)를 {len(chunks)}개 청크로 분할하였습니다.")
    return chunks

def _fallback_process_with_threading(
    conversation_chunk: str, 
    shop_name: Optional[str],
    original_user_prompt_for_fallback: str, 
    tools_for_fallback: List[Dict],
    available_products: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    메인 스트리밍 실패 시, 필요한 경우 입력을 청크로 나누어 병렬로 API 호출을 시도합니다.
    (대체 호출: tool 사용 강제, thinking 미사용)
    """
    print("대체 처리 시작 (병렬 가능)...")
    logging.info("대체 처리 시작 (병렬 가능)...")
    
    fallback_system_prompt = f"""
당신은 카카오톡 대화에서 주문 정보를 추출하는 데이터 분석 전문가입니다.
사용자가 제공한 대화 내용을 분석하여 주문 정보를 추출하고, 반드시 'extract_order_info' 도구를 사용하여 JSON 형식으로 결과를 반환해야 합니다.
절대로 일반 텍스트나 마크다운으로 응답하지 마십시오. 오직 'extract_order_info' 도구만을 사용한 JSON 응답만 허용됩니다.

[도구 사용 규칙]
1. 제공된 대화에서 모든 주문 관련 정보를 면밀히 분석합니다.
2. 'extract_order_info' 도구를 사용하여 분석된 정보를 지정된 JSON 스키마에 맞춰 구성합니다.
3. 응답은 반드시 도구를 통해 그 도구의 'input_schema'에 정의된 JSON 구조로 반환되어야 합니다. (예: <tool_use name="extract_order_info">JSON_데이터</tool_use> 와 유사한 내부적 도구 호출 결과)
4. JSON 데이터는 도구의 input_schema를 엄격히 준수해야 합니다: {json.dumps(tools_for_fallback[0]["input_schema"], ensure_ascii=False, indent=2)}
5. 어떤 상황에서도 일반 텍스트 응답, 설명, 주석 등을 포함해서는 안 됩니다.

주문 정보 추출 시 다음 사항에 유의하세요:
- 판매자가 올린 공지와 고객 주문 구분
- 동일인, 동일 품목 중복 주문 시 최신으로 반영
- 품목명, 주문자명, 수량 정확히 추출
- 시간 순서대로 정리된 주문 목록, 품목별 요약, 주문자별 요약 정보를 제공합니다.
5. 누락된 주문 내역이 없도록 표시하고, 데이터는 생략하거나 "**외 n명, **등 n명처럼" 약식으로 기재하지 않고 전체 값을 모두 제공합니다.
6. 대화에서 "마감"으로 표시된 상품은 판매가 종료된 상품입니다.
7. 주문 패턴 분석에서는 시간대별 주문 건수, 인기 상품, 품절 상품을 추출하세요.

최대한 많은 정보를 추출하되, 어떤 경우에도 'extract_order_info' 도구를 통해서만 응답하세요.
"""
    if shop_name:
        fallback_system_prompt += f"\n분석 중인 대화는 '{shop_name}' 관련 내용입니다."

    text_to_process_for_fallback = original_user_prompt_for_fallback

    if len(text_to_process_for_fallback) > 15000:
        logging.info(f"대체 처리: 입력 텍스트가 15,000자를 초과 ({len(text_to_process_for_fallback)}자). 분할 및 병렬 처리 시작.")
        print(f"대체 처리: 입력 텍스트가 15,000자를 초과 ({len(text_to_process_for_fallback)}자). 분할 및 병렬 처리 시작.")
        
        text_chunks_for_fallback = _split_input_text(text_to_process_for_fallback, max_length=15000)
        logging.info(f"대체 처리: 텍스트가 {len(text_chunks_for_fallback)}개 청크로 분할됨.")
        
        all_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(text_chunks_for_fallback), 3)) as executor:
            future_to_chunk_index = {
                executor.submit(
                    _process_fallback_chunk, 
                    chunk_text, i, len(text_chunks_for_fallback), 
                    shop_name, fallback_system_prompt, tools_for_fallback
                ): i for i, chunk_text in enumerate(text_chunks_for_fallback)
            }
            for future in concurrent.futures.as_completed(future_to_chunk_index):
                chunk_idx = future_to_chunk_index[future]
                try:
                    result = future.result()
                    if result: all_results.append(result)
                except Exception as exc:
                    logging.error(f"대체 처리 청크 {chunk_idx} 실행 중 예외: {exc}\n{traceback.format_exc()}")

        if all_results:
            logging.info(f"대체 처리: {len(all_results)}개 청크 결과 병합 중")
            merged_result = _merge_chunk_results(all_results)
            log_file_path = _save_api_response_to_file(json.dumps(merged_result, ensure_ascii=False), f"{shop_name}_fallback_merged")
            logging.info(f"대체 처리: 병합된 결과가 {log_file_path} 파일에 저장됨.")
            return _validate_and_process_result(merged_result, conversation_chunk)
        else:
            logging.warning("대체 처리 (병렬): 모든 분할 청크에서 유효한 결과를 얻지 못함. 기본 JSON 구조 생성.")
            return _create_default_result(available_products, shop_name)
    else:
        logging.info(f"대체 처리: 입력 텍스트가 짧음 ({len(text_to_process_for_fallback)}자). 단일 대체 호출 시도.")
        print(f"대체 처리: 입력 텍스트가 짧음 ({len(text_to_process_for_fallback)}자). 단일 대체 호출 시도.")
        single_fallback_result = _process_fallback_chunk(
            chunk_text=text_to_process_for_fallback, chunk_index=0, total_chunks=1,
            shop_name=shop_name, system_prompt_for_fallback_chunk=fallback_system_prompt,
            tools_for_fallback_chunk=tools_for_fallback
        )
        if single_fallback_result:
            log_file_path = _save_api_response_to_file(json.dumps(single_fallback_result, ensure_ascii=False), f"{shop_name}_fallback_single")
            logging.info(f"대체 처리(단일): 결과가 {log_file_path} 파일에 저장됨.")
            return _validate_and_process_result(single_fallback_result, conversation_chunk)
        else:
            logging.warning("대체 처리 (단일): 유효한 결과를 얻지 못함. 기본 JSON 구조 생성.")
            print("대체 처리 (단일): 유효한 결과를 얻지 못함. 기본 JSON 구조 생성.")
            return _create_default_result(available_products, shop_name)
    
def _process_fallback_chunk(
    chunk_text: str, 
    chunk_index: int, 
    total_chunks: int, 
    shop_name: Optional[str], 
    system_prompt_for_fallback_chunk: str, 
    tools_for_fallback_chunk: List[Dict]
) -> Optional[Dict[str, Any]]:
    """
    대체 처리 시 개별 청크를 LLM으로 분석합니다. (병렬 실행용, tool 사용 강제)
    """
    logging.info(f"대체 처리 청크 {chunk_index+1}/{total_chunks} 분석 시작 (길이: {len(chunk_text)}자)")
    print(f"대체 처리 청크 {chunk_index+1}/{total_chunks} 분석 시작 (길이: {len(chunk_text)}자)")
    
    result_json_obj = None
    full_text_content_stream = "" 
    tool_input_json_parts = [] 
    tool_actually_used = False

    try:
        # 표준 client.messages.create 사용, thinking 제거, tool_choice 강제, temperature 0.1
        stream_response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=4096, # 도구 사용 시에는 결과 JSON 크기에 맞춰 적절히 조절
            system=system_prompt_for_fallback_chunk,
            temperature=0.1,
            tools=tools_for_fallback_chunk,
            tool_choice={"type": "tool", "name": "extract_order_info"},
            stream=True,
            messages=[
                {"role": "user", "content": chunk_text}
            ]
        )

        stream_log_filename = f"fallback_chunk_{chunk_index+1}_stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "fallback_stream_chunks"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stream_log_path = logs_dir / stream_log_filename

        with open(stream_log_path, 'w', encoding='utf-8') as log_f:
            log_f.write(f"===== 대체 처리 청크 {chunk_index+1}/{total_chunks} 스트리밍 로그 시작 =====\n")
            log_f.write(f"System Prompt Hash: {hash(system_prompt_for_fallback_chunk)}\n") # 프롬프트 변경 확인용
            log_f.write(f"User Content (first 200 chars): {chunk_text[:200]}...\n{'-'*60}\n")

            for chunk_item in stream_response:
                log_f.write(f"Chunk Type: {chunk_item.type}\n")
                if hasattr(chunk_item, 'index') and chunk_item.index is not None: log_f.write(f"Index: {chunk_item.index}\n")

                if chunk_item.type == 'message_start':
                    log_f.write(f"  Role: {chunk_item.message.role}, Model: {chunk_item.message.model}\n")
                elif chunk_item.type == 'content_block_start':
                    if chunk_item.content_block.type == 'tool_use':
                        tool_actually_used = True
                        log_f.write(f"  Tool Use Start: Name: {chunk_item.content_block.name}, ID: {chunk_item.content_block.id}\n")
                elif chunk_item.type == 'content_block_delta':
                    if chunk_item.delta.type == 'text_delta':
                        full_text_content_stream += chunk_item.delta.text
                        log_f.write(f"  Text Delta: '{chunk_item.delta.text}'\n")
                    elif chunk_item.delta.type == 'input_json_delta':
                        if tool_actually_used:
                            tool_input_json_parts.append(chunk_item.delta.partial_json)
                            log_f.write(f"  Input JSON Delta (Partial): '{chunk_item.delta.partial_json}'\n")
                elif chunk_item.type == 'message_delta':
                    log_f.write(f"  Message Delta: Stop Reason: {chunk_item.delta.stop_reason}, Stop Seq: {chunk_item.delta.stop_sequence}\n")
                    if hasattr(chunk_item, 'usage') and chunk_item.usage:
                         log_f.write(f"  Usage: Input: {chunk_item.usage.input_tokens}, Output: {chunk_item.usage.output_tokens}\n")
                log_f.write(f"{'-'*60}\n")
        
        logging.info(f"대체 처리 청크 {chunk_index+1}: 스트리밍 완료. 로그: {stream_log_path}")

        if tool_actually_used and tool_input_json_parts:
            complete_tool_input_json_str = "".join(tool_input_json_parts)
            logging.info(f"대체 처리 청크 {chunk_index+1}: 합쳐진 도구 입력 JSON (길이 {len(complete_tool_input_json_str)}): {complete_tool_input_json_str[:300]}...")
            
            raw_json_dir = pathlib.Path(__file__).parent.parent / "logs" / "fallback_raw_json"
            raw_json_dir.mkdir(parents=True, exist_ok=True)
            raw_json_path = raw_json_dir / f"fallback_raw_tool_json_chunk_{chunk_index+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(raw_json_path, 'w', encoding='utf-8') as f: f.write(complete_tool_input_json_str)
            logging.info(f"대체 처리 청크 {chunk_index+1}: 원본 도구 JSON 저장됨: {raw_json_path}")

            try:
                result_json_obj = json.loads(complete_tool_input_json_str)
                logging.info(f"대체 처리 청크 {chunk_index+1}: 도구 입력 JSON 파싱 성공.")
            except json.JSONDecodeError as e_json:
                logging.error(f"대체 처리 청크 {chunk_index+1}: 도구 입력 JSON 파싱 오류 ({e_json}). 원본: {complete_tool_input_json_str[:500]}")
                try:
                    fixed_json = _fix_json_string(complete_tool_input_json_str)
                    result_json_obj = json.loads(fixed_json)
                    logging.info(f"대체 처리 청크 {chunk_index+1}: 수정된 도구 JSON 파싱 성공.")
                except Exception as e_fix:
                    logging.error(f"대체 처리 청크 {chunk_index+1}: 수정된 도구 JSON 파싱도 실패 ({e_fix}).")
        
        if result_json_obj is None and full_text_content_stream:
            logging.info(f"대체 처리 청크 {chunk_index+1}: 도구 결과 없고 텍스트 응답 있음, JSON 추출 시도.")
            result_json_obj = _extract_json_from_text(full_text_content_stream)
            if result_json_obj:
                 logging.info(f"대체 처리 청크 {chunk_index+1}: 텍스트에서 JSON 추출 성공.")
            else:
                 logging.warning(f"대체 처리 청크 {chunk_index+1}: 텍스트에서 JSON 추출 실패.")

        if result_json_obj:
            logging.info(f"대체 처리 청크 {chunk_index+1}: 유효한 JSON 결과 추출 성공.")
            _save_api_response_to_file(json.dumps(result_json_obj, ensure_ascii=False), f"{shop_name}_fallback_chunk_{chunk_index+1}")
            return result_json_obj
        else:
            logging.warning(f"대체 처리 청크 {chunk_index+1}: 최종적으로 결과 추출 실패.")
            return None

    except anthropic.APIError as e_api:
        logging.error(f"대체 처리 청크 {chunk_index+1} Anthropic API 오류: {str(e_api)}\n{traceback.format_exc()}")
        return None
    except Exception as e_gen:
        logging.error(f"대체 처리 청크 {chunk_index+1} 분석 중 일반 오류 발생: {str(e_gen)}\n{traceback.format_exc()}")
        return None

def _create_default_result(available_products: Optional[Set[str]] = None, shop_name: Optional[str] = None) -> Dict[str, Any]:
    """
    기본 결과 구조를 생성합니다.
    
    Args:
        available_products (Set[str], optional): 추출된 상품 목록
        shop_name (str, optional): 상점 이름
        
    Returns:
        dict: 기본 결과 구조
    """
    logging.info("최소 JSON 구조 생성 중")
    print("최소 JSON 구조 생성 중")
    
    result = {
        "time_based_orders": [],
        "item_based_summary": [],
        "customer_based_orders": [],
        "table_summary": {
            "headers": ["품목", "총수량", "주문자"],
            "rows": []
        },
        "order_pattern_analysis": {
            "peak_hours": [],
            "popular_items": [],
            "sold_out_items": []
        }
    }
    
    if shop_name:
        result["shop_name"] = shop_name
    
    # 상품 목록이 있으면 기본 item_based_summary 생성
    if available_products:
        for product in available_products:
            result["item_based_summary"].append({
                "item": product,
                "total_quantity": 0,
                "customers": ""
            })
    
    return result

def _merge_chunk_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    여러 청크에서 얻은 결과를 병합합니다.
    
    Args:
        results (list): 분석 결과 리스트
        
    Returns:
        dict: 병합된 결과
    """
    if not results:
        return {}
    
    # 첫 번째 결과를 기준으로 설정
    merged = results[0].copy()
    
    # 배열 형태 필드 병합
    array_fields = ["time_based_orders", "item_based_summary", "customer_based_orders"]
    for field in array_fields:
        if field not in merged:
            merged[field] = []
            
        # 나머지 결과에서 해당 필드 병합
        for result in results[1:]:
            if field in result and isinstance(result[field], list):
                merged[field].extend(result[field])
    
    # item_based_summary 중복 제거 및 통합
    if "item_based_summary" in merged:
        item_dict = {}
        for item in merged["item_based_summary"]:
            if "item" not in item or not item["item"]:
                continue
                
            item_name = item["item"]
            if item_name not in item_dict:
                item_dict[item_name] = item.copy()
            else:
                # 수량 합산
                try:
                    current_qty = item_dict[item_name].get("total_quantity", 0)
                    new_qty = item.get("total_quantity", 0)
                    
                    # 문자열을 숫자로 변환
                    if isinstance(current_qty, str):
                        current_qty = int(current_qty.replace(",", ""))
                    if isinstance(new_qty, str):
                        new_qty = int(new_qty.replace(",", ""))
                        
                    item_dict[item_name]["total_quantity"] = current_qty + new_qty
                except (ValueError, TypeError):
                    # 변환 실패 시 원래 값 유지
                    pass
                
                # 고객 목록 병합
                current_customers = item_dict[item_name].get("customers", "")
                new_customers = item.get("customers", "")
                
                if current_customers and new_customers:
                    current_set = set(c.strip() for c in current_customers.split(","))
                    new_set = set(c.strip() for c in new_customers.split(","))
                    merged_set = current_set.union(new_set)
                    item_dict[item_name]["customers"] = ", ".join(sorted(list(merged_set)))
                elif new_customers:
                    item_dict[item_name]["customers"] = new_customers
        
        merged["item_based_summary"] = list(item_dict.values())
    
    # order_pattern_analysis 병합
    if "order_pattern_analysis" in merged:
        for result in results[1:]:
            if "order_pattern_analysis" not in result:
                continue
                
            for field in ["peak_hours", "popular_items", "sold_out_items"]:
                if field in result["order_pattern_analysis"] and isinstance(result["order_pattern_analysis"][field], list):
                    if field not in merged["order_pattern_analysis"]:
                        merged["order_pattern_analysis"][field] = []
                    
                    merged["order_pattern_analysis"][field].extend(result["order_pattern_analysis"][field])
        
        # 중복 제거
        for field in ["peak_hours", "popular_items", "sold_out_items"]:
            if field in merged["order_pattern_analysis"]:
                merged["order_pattern_analysis"][field] = list(set(merged["order_pattern_analysis"][field]))
    
    logging.info(f"청크 결과 병합 완료: time_based_orders={len(merged.get('time_based_orders', []))}, "
                f"item_based_summary={len(merged.get('item_based_summary', []))}, "
                f"customer_based_orders={len(merged.get('customer_based_orders', []))}")
    
    return merged

def _validate_and_process_result(result: Dict[str, Any], preprocessed_text: str) -> Dict[str, Any]:
    """
    LLM 결과를 검증하고, 코드 기반으로 item/table 요약 정보를 생성하여 최종 결과를 만듭니다.
    
    Args:
        result (dict): LLM 분석 결과 (time_based_orders, customer_based_orders, order_pattern_analysis 포함 기대)
        preprocessed_text (str): 전처리된 대화 내용 (현재는 사용되지 않음)
        
    Returns:
        dict: 검증 및 모든 정보가 포함된 최종 결과
    """
    # LLM 결과에서 필요한 기본 필드 확인 및 초기화
    if not isinstance(result, dict):
        print("⚠️ 경고: LLM 결과가 유효한 딕셔너리가 아닙니다.")
        result = {}

    llm_time_orders = result.get("time_based_orders", [])
    if not isinstance(llm_time_orders, list):
        print("⚠️ 경고: LLM 결과에서 'time_based_orders'가 유효하지 않습니다.")
        llm_time_orders = []

    llm_customer_orders = result.get("customer_based_orders", [])
    if not isinstance(llm_customer_orders, list):
         print("⚠️ 경고: LLM 결과에서 'customer_based_orders'가 유효하지 않습니다.")
         llm_customer_orders = []

    llm_pattern_analysis = result.get("order_pattern_analysis", {})
    if not isinstance(llm_pattern_analysis, dict):
         print("⚠️ 경고: LLM 결과에서 'order_pattern_analysis'가 유효하지 않습니다.")
         llm_pattern_analysis = {"peak_hours": [], "popular_items": [], "sold_out_items": []}

    # LLM이 생성한 time_based_orders/customer_based_orders 검증 (필요 시)
    # 예: llm_time_orders = filter_invalid_items(llm_time_orders)
    #     llm_customer_orders = filter_invalid_items(llm_customer_orders)
    print(f"LLM 추출 time_based_orders: {len(llm_time_orders)}개 주문")
    print(f"LLM 추출 customer_based_orders: {len(llm_customer_orders)}개 주문 (고객별 상세)")

    # time_based_orders를 기반으로 item/table 요약 정보 생성
    generated_summaries = _generate_item_and_table_summaries(llm_time_orders)

    # 최종 결과 조합
    final_result = {
        "time_based_orders": llm_time_orders,
        "customer_based_orders": llm_customer_orders, # LLM 결과 사용
        "item_based_summary": generated_summaries["item_based_summary"], # 코드 생성 결과 사용
        "table_summary": generated_summaries["table_summary"], # 코드 생성 결과 사용
        "order_pattern_analysis": llm_pattern_analysis
    }

    # 결과 요약 로그 출력
    print(f"코드 생성 item_based_summary: {len(final_result.get('item_based_summary', []))}개 품목")
    print(f"코드 생성 table_summary: {len(final_result.get('table_summary', {}).get('rows', []))}개 행")

    # 주문 패턴 분석 검증 (기존 로직 활용 또는 수정)
    if "order_pattern_analysis" in final_result and isinstance(final_result["order_pattern_analysis"], dict):
        if "sold_out_items" in final_result["order_pattern_analysis"] and isinstance(final_result["order_pattern_analysis"]["sold_out_items"], list):
            original_count = len(final_result["order_pattern_analysis"]["sold_out_items"])
            final_result["order_pattern_analysis"]["sold_out_items"] = [
                item for item in final_result["order_pattern_analysis"]["sold_out_items"]
                if isinstance(item, str) and is_valid_item_name(item)
            ]
            filtered_count = original_count - len(final_result["order_pattern_analysis"]["sold_out_items"])
            if filtered_count > 0:
                print(f"sold_out_items에서 {filtered_count}개의 잘못된 품목이 필터링되었습니다.")

    # 빈 배열/데이터 확인 로그 (선택 사항)
    # ... (기존과 유사하게 필요한 검사 추가) ...
    
    return final_result

def _generate_item_and_table_summaries(time_based_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    time_based_orders 데이터를 기반으로 item_based_summary와 table_summary를 생성합니다.
    pandas 없이 구현됩니다.

    Args:
        time_based_orders: LLM이 추출한 시간순 주문 목록

    Returns:
        생성된 item_based_summary와 table_summary를 담은 딕셔너리
    """
    item_summary_data = defaultdict(lambda: {'total_quantity': 0, 'customers': set()})

    # 수량 타입 변환 함수 (오류 처리 포함)
    def safe_int(value):
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.replace(',', ''))
            except ValueError:
                return 0
        return 0

    # 1. 데이터 집계 (item_based_summary 준비)
    for order in time_based_orders:
        item_name = order.get('item')
        customer_name = order.get('customer')
        quantity = safe_int(order.get('quantity', 0))

        if not item_name or not customer_name or quantity <= 0:
            continue

        # 품목별 요약 데이터 업데이트
        item_summary_data[item_name]['total_quantity'] += quantity
        item_summary_data[item_name]['customers'].add(customer_name)

    # 2. item_based_summary 생성
    item_based_summary = []
    for item_name, data in item_summary_data.items():
        item_based_summary.append({
            'item': item_name,
            'total_quantity': data['total_quantity'],
            'customers': ', '.join(sorted(list(data['customers'])))
        })
    item_based_summary = sorted(item_based_summary, key=lambda x: x['total_quantity'], reverse=True)

    # 3. table_summary 생성
    table_summary_rows = []
    for item_data in item_based_summary: # item_based_summary 결과를 사용
         table_summary_rows.append([
             item_data['item'],
             str(item_data['total_quantity']),
             item_data['customers']
         ])
    table_summary = {
        'headers': ["품목", "총수량", "주문자"],
        'rows': table_summary_rows
    }

    return {
        "item_based_summary": item_based_summary,
        "table_summary": table_summary,
    }

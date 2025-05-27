from typing import List, Dict, Any, Optional, Set
import json
import os
from datetime import datetime
import pathlib  # Add import for path handling
import traceback

from utils.text_processing import filter_conversation_by_date
from services.preprocess_chat import ChatPreprocessor
from services.llm_service import analyze_conversation_chunk  # 기존 함수 재사용

# 분석 결과 저장소 (실제로는 DB 사용 권장)
analysis_results = {}
chat_preprocessor = ChatPreprocessor()

async def analyze_specific_products_task(
    job_id: str,
    conversation: str,
    product_names: List[str],
    shop_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """상품 특화 분석 백그라운드 작업"""
    try:
        # 상태 업데이트
        analysis_results[job_id] = {"status": "processing"}
        
        # 1. 대화 전처리 (기존 코드 재활용)
        preprocessed_text = conversation
        if start_date or end_date:
            preprocessed_text = filter_conversation_by_date(conversation, start_date, end_date)
        
        # 2. 불필요한 메시지 제거 (기존 코드 재활용)
        try:
            preprocessed_text = chat_preprocessor.preprocess_chat(preprocessed_text)
        except Exception as e:
            print(f"대화 전처리 중 오류: {str(e)}")
            # 계속 진행
        
        # 3. 상품명 목록 정리 (사용자 입력)
        product_list_for_llm = set(product_names)
        
        print(f"LLM에 전달될 상품 목록 (analyze_conversation_chunk): {len(product_list_for_llm)}개")
        print(f"상품 목록 상세: {list(product_list_for_llm)}")
        
        # 4. 분석 실행 (기존 함수 재활용)
        result = analyze_conversation_chunk(
            conversation_chunk=preprocessed_text, 
            shop_name=shop_name,
            product_list_for_llm=product_list_for_llm
        )
        
        # 5. 결과에 상품 필터링 정보 추가 (감사 추적용)
        result["analyzed_products"] = list(product_list_for_llm)
        
        # 6. 결과 저장
        analysis_results[job_id] = {
            "status": "completed", 
            "result": result
        }
        
        # 7. 결과를 파일로도 저장 (영구 보존)
        _save_result_to_file(job_id, analysis_results[job_id])
        
    except Exception as e:
        # 오류 처리
        error_info = {
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        analysis_results[job_id] = error_info
        
        # 오류 정보도 파일로 저장
        _save_result_to_file(job_id, error_info)

def _save_result_to_file(job_id: str, result_data: Dict[str, Any]):
    """분석 결과를 파일로 저장"""
    try:
        # 결과 저장 디렉토리 생성
        results_dir = pathlib.Path(__file__).parent.parent / "logs" / "analysis_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성
        file_path = results_dir / f"{job_id}.json"
        
        # 결과 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
            
        print(f"분석 결과가 {file_path} 파일에 저장되었습니다.")
    except Exception as e:
        print(f"결과 저장 중 오류 발생: {str(e)}")

def get_analysis_result(job_id: str) -> Dict[str, Any]:
    """결과 조회 함수 (메모리와 파일 모두 확인)"""
    # 1. 메모리에서 결과 확인
    if job_id in analysis_results:
        return analysis_results[job_id]
    
    # 2. 메모리에 없으면 파일에서 확인
    try:
        results_dir = pathlib.Path(__file__).parent.parent / "logs" / "analysis_results"
        file_path = results_dir / f"{job_id}.json"
        
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                # 메모리에도 캐싱
                analysis_results[job_id] = result_data
                return result_data
    except Exception as e:
        print(f"파일에서 결과 불러오기 중 오류: {str(e)}")
    
    # 3. 결과가 없으면 not_found 반환
    return {"status": "not_found"}
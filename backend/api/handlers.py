import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from services.llm_service import analyze_conversation
from services.export_service import generate_csv_from_data
from fastapi.concurrency import run_in_threadpool

# 작업 상태 저장소
analysis_jobs: Dict[str, Dict[str, Any]] = {}

async def handle_analyze_chat(conversation: str, start_date: Optional[str], end_date: Optional[str], shop_name: Optional[str]) -> Dict[str, Any]:
    """
    대화 내용을 분석하는 핸들러.
    
    Args:
        conversation: 대화 내용
        start_date: 시작일 (ISO 형식)
        end_date: 종료일 (ISO 형식)
        shop_name: 상점 이름
        
    Returns:
        분석 작업 생성 결과
    """
    try:
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        
        # 초기 상태 저장
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(conversation),
            "shop_name": shop_name,
            "start_date": start_date,
            "end_date": end_date,
            "result": None,
            "error": None
        }
        
        return {
            "success": True,
            "job_id": job_id
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def handle_analyze_file(file_content: str, shop_name: Optional[str], start_date: Optional[str], end_date: Optional[str], filename: Optional[str] = None) -> Dict[str, Any]:
    """
    파일 내용을 분석하는 핸들러.
    
    Args:
        file_content: 파일 내용 문자열
        shop_name: 상점 이름
        start_date: 시작일 (ISO 형식)
        end_date: 종료일 (ISO 형식)
        filename: 파일 이름
        
    Returns:
        분석 작업 생성 결과
    """
    try:
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        
        # 초기 상태 저장
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(file_content),
            "shop_name": shop_name,
            "start_date": start_date,
            "end_date": end_date,
            "file_name": filename,
            "result": None,
            "error": None
        }
        
        return {
            "success": True,
            "job_id": job_id
        }
        
    except Exception as e:
        print(f"파일 분석 오류: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

async def handle_get_result(job_id: str) -> Dict[str, Any]:
    """
    작업 결과를 조회하는 핸들러.
    
    Args:
        job_id: 작업 ID
        
    Returns:
        작업 결과 정보
    """
    job = analysis_jobs.get(job_id)
    
    if not job:
        return {
            "status": "not_found",
            "error": "해당 작업을 찾을 수 없습니다"
        }
    
    return {
        "status": job["status"],
        "result": job["result"],
        "error": job["error"]
    }

async def handle_generate_csv(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    CSV 파일을 생성하는 핸들러.
    
    Args:
        data: 분석 결과 데이터
        
    Returns:
        생성된 CSV 데이터
    """
    try:
        result = generate_csv_from_data(data)
        return {
            "success": True,
            "data": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def handle_list_jobs() -> Dict[str, Dict[str, Any]]:
    """
    모든 작업 목록을 조회하는 핸들러.
    
    Returns:
        작업 목록 정보
    """
    return {
        job_id: {
            "status": job["status"],
            "start_time": job["start_time"],
            "conversation_length": job["conversation_length"],
            "shop_name": job["shop_name"],
            "start_date": job.get("start_date"),
            "end_date": job.get("end_date"),
            "file_name": job.get("file_name"),
            "has_result": job["result"] is not None
        }
        for job_id, job in analysis_jobs.items()
    }

async def process_conversation_task(job_id: str, conversation: str, start_date: Optional[str] = None, end_date: Optional[str] = None, shop_name: Optional[str] = None) -> None:
    """
    백그라운드에서 대화 분석을 처리하는 태스크.
    
    Args:
        job_id: 작업 ID
        conversation: 대화 내용
        start_date: 시작일 (ISO 형식)
        end_date: 종료일 (ISO 형식)
        shop_name: 상점 이름
    """
    try:
        # 대화 분석 요청
        analysis_jobs[job_id]["status"] = "analyzing"
        
        # LLM 서비스로 분석 요청 (별도 스레드에서 실행하여 이벤트 루프 블로킹 방지)
        result = await run_in_threadpool(
            analyze_conversation,
            conversation,
            start_date,
            end_date,
            shop_name
        )
        
        # 분석 결과 확인
        if "error" in result:
            analysis_jobs[job_id]["status"] = "failed"
            analysis_jobs[job_id]["error"] = result.get("message", "분석 중 오류가 발생했습니다")
        else:
            # 성공적으로 분석 완료
            analysis_jobs[job_id]["status"] = "completed"
            analysis_jobs[job_id]["result"] = result
            
            # shop_name 저장
            if shop_name:
                result["shop_name"] = shop_name
            
            # 응답 데이터 로그 저장
            with open(f"analysis_log_{job_id}.json", "w", encoding="utf-8") as log_file:
                json.dump(result, log_file, ensure_ascii=False, indent=2)
                print(f"분석 결과가 analysis_log_{job_id}.json 파일에 저장되었습니다.")
                
    except Exception as e:
        # 오류 발생 시
        analysis_jobs[job_id]["status"] = "failed"
        analysis_jobs[job_id]["error"] = str(e)
        print(f"분석 중 오류 발생: {str(e)}")

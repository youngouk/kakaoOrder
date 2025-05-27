import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from services.llm_service import analyze_conversation
from services.analysis_service import analyze_conversation_with_progress, analyze_conversation_with_progress_callback
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
        
        # 초기 상태 저장 및 초기 진행 로그 추가
        initial_logs = [{
            "phase": "분석 시작",
            "progress": 5,
            "details": [
                f"상점명: {shop_name or '미지정'}",
                f"분석 기간: {start_date or '전체'} ~ {end_date or '전체'}"
            ],
            "timestamp": datetime.now().isoformat()
        }]
        
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(conversation),
            "shop_name": shop_name,
            "start_date": start_date,
            "end_date": end_date,
            "result": None,
            "error": None,
            "progress_logs": initial_logs,  # 초기 로그 포함
            "current_phase": "initializing"
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
        
        # 초기 상태 저장 및 초기 진행 로그 추가
        initial_logs = [{
            "phase": "분석 시작",
            "progress": 5,
            "details": [
                f"상점명: {shop_name or '미지정'}",
                f"파일명: {filename or '미지정'}",
                f"분석 기간: {start_date or '전체'} ~ {end_date or '전체'}"
            ],
            "timestamp": datetime.now().isoformat()
        }]
        
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(file_content),
            "shop_name": shop_name,
            "start_date": start_date,
            "end_date": end_date,
            "file_name": filename,
            "result": None,
            "error": None,
            "progress_logs": initial_logs,  # 초기 로그 포함
            "current_phase": "initializing"
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
    
    # 진행상태 정보도 함께 반환 (안전한 get 메서드 사용)
    response = {
        "status": job.get("status", "processing"),
        "result": job.get("result"),
        "error": job.get("error")
    }
    
    # 진행상태 로그가 있으면 포함 (더 안전한 체크)
    progress_logs = job.get("progress_logs", [])
    if progress_logs and isinstance(progress_logs, list) and len(progress_logs) > 0:
        response["progress_logs"] = progress_logs
        # 최신 진행률 정보도 추가
        try:
            latest_log = progress_logs[-1]
            if isinstance(latest_log, dict) and "progress" in latest_log:
                response["progress"] = latest_log["progress"]
        except (IndexError, KeyError) as e:
            # 에러 무시하고 계속
            pass
    
    # 현재 단계 정보가 있으면 포함
    if "current_phase" in job:
        response["current_phase"] = job.get("current_phase", "unknown")
    
    return response

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
        # 백그라운드 작업 시작 시 progress_logs가 없으면 초기화
        if job_id in analysis_jobs and "progress_logs" not in analysis_jobs[job_id]:
            analysis_jobs[job_id]["progress_logs"] = [{
                "phase": "백그라운드 작업 시작",
                "progress": 1,
                "details": ["분석 준비 중..."],
                "timestamp": datetime.now().isoformat()
            }]
        
        # 대화 분석 요청
        analysis_jobs[job_id]["status"] = "analyzing"
        analysis_jobs[job_id]["current_phase"] = "loading"
        
        # 진행상태 업데이트를 위한 콜백 함수 정의
        def update_progress_logs(status_dict):
            # status_dict는 get_status()의 반환값이므로 logs를 추출해야 함
            if isinstance(status_dict, dict) and "logs" in status_dict:
                analysis_jobs[job_id]["progress_logs"] = status_dict["logs"]
            elif isinstance(status_dict, list):
                # 이미 리스트인 경우 그대로 사용
                analysis_jobs[job_id]["progress_logs"] = status_dict
            else:
                # 예상치 못한 형식인 경우 빈 리스트로 초기화
                print(f"[WARNING] 예상치 못한 progress_logs 형식: {type(status_dict)}")
                analysis_jobs[job_id]["progress_logs"] = []
        
        # 진행상태를 추적하는 새로운 분석 함수 사용
        result = await run_in_threadpool(
            analyze_conversation_with_progress_callback,
            conversation,
            job_id,
            start_date,
            end_date,
            shop_name,
            update_progress_logs
        )
        
        # 최종 진행상태 로그를 작업 정보에 저장
        if "progress_logs" in result:
            analysis_jobs[job_id]["progress_logs"] = result["progress_logs"]
        
        # 분석 결과 확인
        if "error" in result:
            analysis_jobs[job_id]["status"] = "failed"
            analysis_jobs[job_id]["error"] = result.get("message", "분석 중 오류가 발생했습니다")
            analysis_jobs[job_id]["current_phase"] = "failed"
        else:
            # 성공적으로 분석 완료
            analysis_jobs[job_id]["status"] = "completed"
            analysis_jobs[job_id]["result"] = result
            analysis_jobs[job_id]["current_phase"] = "completed"
            
            # shop_name 저장
            if shop_name:
                result["shop_name"] = shop_name
            
            # 분석 완료 시간 기록
            analysis_jobs[job_id]["end_time"] = datetime.now().isoformat()
            
        print(f"✅ 작업 {job_id} 분석 완료: 상태={analysis_jobs[job_id]['status']}")
        
    except Exception as e:
        print(f"❌ 작업 {job_id} 분석 중 오류: {str(e)}")
        analysis_jobs[job_id]["status"] = "failed"
        analysis_jobs[job_id]["error"] = f"분석 처리 중 오류가 발생했습니다: {str(e)}"
        analysis_jobs[job_id]["current_phase"] = "failed"

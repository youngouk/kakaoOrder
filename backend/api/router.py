from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form, Body
from typing import Dict, Any, Optional

from api.models import (
    ConversationRequest, 
    AnalysisResponse, 
    AnalysisStatusResponse,
    CSVGenerationResponse
)
from api.handlers import (
    handle_analyze_chat,
    handle_analyze_file,
    handle_get_result,
    handle_generate_csv,
    handle_list_jobs,
    process_conversation_task
)

# API 라우터 생성
router = APIRouter(prefix="/api")

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_chat(request: ConversationRequest, background_tasks: BackgroundTasks):
    """
    KakaoTalk 대화 내용을 분석하여 주문 정보를 추출합니다.
    """
    if not request.conversation:
        raise HTTPException(status_code=400, detail="대화 내용이 필요합니다")
    
    response = await handle_analyze_chat(
        conversation=request.conversation,
        start_date=request.start_date,
        end_date=request.end_date,
        shop_name=request.shop_name
    )
    
    if response["success"] and "job_id" in response:
        # 백그라운드에서 분석 작업 실행
        background_tasks.add_task(
            process_conversation_task,
            job_id=response["job_id"],
            conversation=request.conversation,
            start_date=request.start_date,
            end_date=request.end_date,
            shop_name=request.shop_name
        )
    
    return AnalysisResponse(
        success=response["success"],
        job_id=response.get("job_id"),
        error=response.get("error")
    )

@router.post("/analyze-file")
async def analyze_chat_from_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    shop_name: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None)
):
    """
    업로드된 TXT 파일에서 KakaoTalk 대화 내용을 분석합니다.
    """
    try:
        # 파일 내용 읽기
        content = await file.read()
        conversation = content.decode('utf-8')
        
        if not conversation.strip():
            return {"success": False, "error": "파일 내용이 비어있습니다"}
        
        response = await handle_analyze_file(
            file_content=conversation,
            shop_name=shop_name,
            start_date=start_date,
            end_date=end_date,
            filename=file.filename
        )
        
        if response["success"] and "job_id" in response:
            # 백그라운드에서 분석 작업 실행
            background_tasks.add_task(
                process_conversation_task,
                job_id=response["job_id"],
                conversation=conversation,
                start_date=start_date,
                end_date=end_date,
                shop_name=shop_name
            )
        
        return response
        
    except Exception as e:
        print(f"파일 분석 오류: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/result/{job_id}", response_model=AnalysisStatusResponse)
async def get_analysis_result(job_id: str):
    """
    특정 작업의 분석 결과를 조회합니다.
    """
    response = await handle_get_result(job_id)
    
    if response["status"] == "not_found":
        raise HTTPException(status_code=404, detail=response["error"])
    
    return AnalysisStatusResponse(
        status=response["status"],
        result=response["result"],
        error=response["error"]
    )

@router.post("/generate-csv", response_model=CSVGenerationResponse)
async def generate_csv(data: Dict[str, Any] = Body(...)):
    """
    분석 데이터에서 CSV 파일을 생성합니다.
    """
    response = await handle_generate_csv(data)
    
    return CSVGenerationResponse(
        success=response["success"],
        data=response.get("data"),
        error=response.get("error")
    )

@router.get("/jobs")
async def list_jobs():
    """
    모든 분석 작업 목록을 조회합니다. (관리자용 엔드포인트)
    """
    # 실제 운영 환경에서는 인증을 추가해야 합니다
    return await handle_list_jobs()

@router.get("/health")
async def health_check():
    """
    API 서버 상태를 확인합니다.
    """
    return {"status": "ok"}

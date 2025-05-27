from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.specific_product_service import analyze_specific_products_task, get_analysis_result
from datetime import datetime
import uuid

router = APIRouter()

class SpecificProductRequest(BaseModel):
    shop_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    conversation: str
    product_names: List[str]  # 상품명 목록 (1-20개)

@router.post("/analyze-specific-products")
async def analyze_products_endpoint(
    request: SpecificProductRequest,
    background_tasks: BackgroundTasks
):
    # 입력 검증
    if not request.conversation:
        raise HTTPException(status_code=400, detail="대화 내용이 비어있습니다")
    
    if not request.product_names:
        raise HTTPException(status_code=400, detail="조회할 상품명이 비어있습니다")
    
    if len(request.product_names) > 20:
        raise HTTPException(status_code=400, detail="상품명은 최대 20개까지 입력 가능합니다")
    
    # 작업 ID 생성
    job_id = f"product_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # 백그라운드 작업 시작 (기존 시스템과 유사)
    background_tasks.add_task(
        analyze_specific_products_task,
        job_id=job_id,
        conversation=request.conversation,
        product_names=request.product_names,
        shop_name=request.shop_name,
        start_date=request.start_date,
        end_date=request.end_date
    )
    
    return {"success": True, "job_id": job_id, "error": None}

@router.get("/result/{job_id}")
async def get_specific_product_result(job_id: str):
    """상품 분석 결과 조회 API"""
    result = get_analysis_result(job_id)
    
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"분석 작업 {job_id}를 찾을 수 없습니다")
    
    return result
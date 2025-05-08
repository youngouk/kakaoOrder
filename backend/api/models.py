from pydantic import BaseModel
from typing import Optional, Dict, Any, List

# 분석 요청 모델
class ConversationRequest(BaseModel):
    conversation: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    shop_name: Optional[str] = None

# 분석 응답 모델
class AnalysisResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    job_id: Optional[str] = None

# 분석 상태 응답 모델
class AnalysisStatusResponse(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None

# CSV 생성 요청 모델
class CSVGenerationRequest(BaseModel):
    data: Dict[str, Any]

# CSV 생성 응답 모델
class CSVGenerationResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, str]] = None
    error: Optional[str] = None

# 작업 목록 응답 모델
class JobListResponse(BaseModel):
    jobs: Dict[str, Dict[str, Any]]

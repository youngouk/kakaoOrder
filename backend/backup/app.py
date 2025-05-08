from fastapi import FastAPI, HTTPException, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import base64
import json
import uuid
import time
from datetime import datetime
from llm_service import analyze_conversation

# Create FastAPI app
app = FastAPI(title="KakaoOrder API")

# Add CORS middleware to allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MVP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 작업 상태 저장소
analysis_jobs: Dict[str, Dict[str, Any]] = {}

# Define request model
class ConversationRequest(BaseModel):
    conversation: str
    date: Optional[str] = None
    shop_name: Optional[str] = None

# Define response models
class AnalysisResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    job_id: Optional[str] = None

class AnalysisStatusResponse(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_chat(request: ConversationRequest, background_tasks: BackgroundTasks):
    """
    Analyze a KakaoTalk conversation to extract order information
    """
    if not request.conversation:
        raise HTTPException(status_code=400, detail="대화 내용이 필요합니다")
    
    try:
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        
        # 백그라운드에서 분석 작업 실행
        background_tasks.add_task(
            process_conversation,
            job_id=job_id,
            conversation=request.conversation,
            date_str=request.date,
            shop_name=request.shop_name
        )
        
        # 초기 상태 저장
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(request.conversation),
            "shop_name": request.shop_name,
            "date": request.date,
            "result": None,
            "error": None
        }
        
        return AnalysisResponse(success=True, job_id=job_id)
        
    except Exception as e:
        return AnalysisResponse(success=False, error=str(e))

@app.get("/api/result/{job_id}", response_model=AnalysisStatusResponse)
async def get_analysis_result(job_id: str):
    """
    Get the analysis result for a specific job
    """
    if job_id not in analysis_jobs:
        raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다")
    
    job = analysis_jobs[job_id]
    
    return AnalysisStatusResponse(
        status=job["status"],
        result=job["result"],
        error=job["error"]
    )

async def process_conversation(job_id: str, conversation: str, date_str: Optional[str] = None, shop_name: Optional[str] = None):
    """
    Process the conversation analysis in the background
    """
    try:
        # 대화 분석 요청
        analysis_jobs[job_id]["status"] = "analyzing"
        
        # LLM 서비스로 분석 요청
        result = analyze_conversation(
            conversation_text=conversation,
            date_str=date_str,
            shop_name=shop_name
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
                
    except Exception as e:
        # 오류 발생 시
        analysis_jobs[job_id]["status"] = "failed"
        analysis_jobs[job_id]["error"] = str(e)

@app.get("/")
async def root():
    return {"message": "KakaoOrder API is running"}

# Function to generate CSV from analysis data
@app.post("/api/generate-csv")
async def generate_csv(data: dict = Body(...)):
    """
    Generate CSV files from analysis data
    """
    try:
        # Function to convert data to CSV string
        def to_csv(data_list, headers):
            rows = [",".join(headers)]
            for item in data_list:
                row = ",".join([f'"{str(item.get(h, ""))}"' for h in headers])
                rows.append(row)
            return "\n".join(rows)
        
        # Generate CSVs for each data type
        result = {}
        
        if "time_based_orders" in data:
            headers = ["time", "customer", "item", "quantity", "note"]
            csv_data = to_csv(data["time_based_orders"], headers)
            result["time_based_csv"] = base64.b64encode(csv_data.encode()).decode()
        
        if "item_based_summary" in data:
            headers = ["item", "total_quantity", "customers"]
            csv_data = to_csv(data["item_based_summary"], headers)
            result["item_based_csv"] = base64.b64encode(csv_data.encode()).decode()
        
        if "customer_based_orders" in data:
            headers = ["customer", "item", "quantity", "note"]
            csv_data = to_csv(data["customer_based_orders"], headers)
            result["customer_based_csv"] = base64.b64encode(csv_data.encode()).decode()
        
        return {"success": True, "data": result}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# 작업 관리 엔드포인트
@app.get("/api/jobs", response_model=Dict[str, Dict[str, Any]])
async def list_jobs():
    """
    List all analysis jobs (admin endpoint)
    """
    # 실제 운영 환경에서는 인증을 추가해야 합니다
    return {
        job_id: {
            "status": job["status"],
            "start_time": job["start_time"],
            "conversation_length": job["conversation_length"],
            "shop_name": job["shop_name"],
            "date": job["date"],
            "has_result": job["result"] is not None
        }
        for job_id, job in analysis_jobs.items()
    }

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

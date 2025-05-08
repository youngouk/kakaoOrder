from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
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
    conversation: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
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
            start_date=request.start_date,
            end_date=request.end_date,
            shop_name=request.shop_name
        )
        
        # 초기 상태 저장
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(request.conversation),
            "shop_name": request.shop_name,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "result": None,
            "error": None
        }
        
        return AnalysisResponse(success=True, job_id=job_id)
        
    except Exception as e:
        return AnalysisResponse(success=False, error=str(e))

# 파일 분석 엔드포인트
@app.post("/api/analyze-file")
async def analyze_chat_from_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    shop_name: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None)
):
    """
    Analyze a KakaoTalk conversation from an uploaded TXT file
    """
    try:
        # 파일 내용 읽기
        content = await file.read()
        conversation = content.decode('utf-8')
        
        if not conversation.strip():
            return {"success": False, "error": "파일 내용이 비어있습니다"}
        
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        
        # 백그라운드에서 분석 작업 실행
        background_tasks.add_task(
            process_conversation,
            job_id=job_id,
            conversation=conversation,
            start_date=start_date,
            end_date=end_date,
            shop_name=shop_name
        )
        
        # 초기 상태 저장
        analysis_jobs[job_id] = {
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "conversation_length": len(conversation),
            "shop_name": shop_name,
            "start_date": start_date,
            "end_date": end_date,
            "file_name": file.filename,
            "result": None,
            "error": None
        }
        
        return {"success": True, "job_id": job_id}
        
    except Exception as e:
        print(f"파일 분석 오류: {str(e)}")
        return {"success": False, "error": str(e)}

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

async def process_conversation(
    job_id: str, 
    conversation: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    shop_name: Optional[str] = None
):
    """
    Process the conversation analysis in the background
    """
    try:
        # 대화 분석 요청
        analysis_jobs[job_id]["status"] = "analyzing"
        
        # LLM 서비스로 분석 요청
        result = analyze_conversation(
            conversation_text=conversation,
            start_date=start_date,
            end_date=end_date,
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
            
            # 응답 데이터 로그 저장
            with open(f"analysis_log_{job_id}.json", "w", encoding="utf-8") as log_file:
                json.dump(result, log_file, ensure_ascii=False, indent=2)
                print(f"분석 결과가 analysis_log_{job_id}.json 파일에 저장되었습니다.")
                
    except Exception as e:
        # 오류 발생 시
        analysis_jobs[job_id]["status"] = "failed"
        analysis_jobs[job_id]["error"] = str(e)
        print(f"분석 중 오류 발생: {str(e)}")

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
        # CSV 헤더 매핑 정의
        time_header_map = {
            "time": "시간",
            "customer": "주문자",
            "item": "품목",
            "quantity": "수량",
            "note": "비고"
        }
        
        item_header_map = {
            "item": "품목명",
            "total_quantity": "총 수량",
            "customers": "주문자 목록"
        }
        
        customer_header_map = {
            "customer": "주문자",
            "item": "품목",
            "quantity": "수량",
            "note": "비고"
        }
        
        # Function to convert data to CSV string
        def to_csv(data_list, headers, header_map):
            # CSV 헤더 추가
            header_row = []
            for h in headers:
                header_row.append(f'"{header_map[h]}"')
            
            rows = [",".join(header_row)]
            
            # 데이터 행 추가
            for item in data_list:
                row = []
                for h in headers:
                    value = item.get(h, "")
                    if isinstance(value, str):
                        # 특수문자 처리
                        value = value.replace('"', '""')
                        row.append(f'"{value}"')
                    else:
                        row.append(f'"{str(value)}"')
                rows.append(",".join(row))
                
            return "\n".join(rows)
        
        # Generate CSVs for each data type
        result = {}
        
        if "time_based_orders" in data:
            headers = ["time", "customer", "item", "quantity", "note"]
            csv_data = to_csv(data["time_based_orders"], headers, time_header_map)
            result["time_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
        if "item_based_summary" in data:
            headers = ["item", "total_quantity", "customers"]
            csv_data = to_csv(data["item_based_summary"], headers, item_header_map)
            result["item_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
        if "customer_based_orders" in data:
            headers = ["customer", "item", "quantity", "note"]
            csv_data = to_csv(data["customer_based_orders"], headers, customer_header_map)
            result["customer_based_csv"] = base64.b64encode(csv_data.encode("utf-8")).decode()
        
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
            "start_date": job.get("start_date"),
            "end_date": job.get("end_date"),
            "file_name": job.get("file_name"),
            "has_result": job["result"] is not None
        }
        for job_id, job in analysis_jobs.items()
    }

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

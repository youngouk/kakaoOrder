from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import router as main_router
from api.product_router import router as product_router
from config import API_TITLE, API_HOST, API_PORT

# Create FastAPI app
app = FastAPI(title=API_TITLE)

# Add CORS middleware to allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MVP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기존 라우터를 그대로 등록하여 /api/... 경로 유지
app.include_router(main_router)
# 상품 분석 전용 라우터 등록
app.include_router(product_router, prefix="/api/specific")

@app.get("/")
async def root():
    return {"message": "KakaoOrder API is running"}

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import router
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

# Include API router
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "KakaoOrder API is running"}

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)

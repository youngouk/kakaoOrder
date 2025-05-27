# KakaoOrder: Detailed Project Guide

## 1. Introduction
KakaoOrder는 카카오톡 대화 내용을 분석하여 주문 정보를 자동 추출 및 정리하는 웹 서비스입니다. Claude 3.7 Sonnet 기반 LLM을 활용해 시간별, 품목별, 주문자별 주문 데이터를 제공합니다.

## 2. Objectives
- 대규모(3만자) 대화도 효율 처리
- 판매자 메시지에서 상품명, 가격, 마감 정보 정확 추출
- 주문자별·품목별 요약, 교차표 및 패턴 분석
- JSON 및 UTF-8 BOM CSV 내보내기 지원

## 3. Core Components
- **Backend**: FastAPI 비동기 서버 (Python 3.7+)
- **API Layer**: `/api` 라우터, Pydantic 요청/응답 모델
- **Services**: LLM 호출, 전처리, 분석 로직 (`services/`)
- **Utilities**: 텍스트 파싱, 날짜 유틸 (`utils/`)
- **Frontend**: React.js UI, `components/` 내 입력 및 결과 렌더링

## 4. Project Structure
```
kakaoOrder/
├─ backend/
│  ├─ main.py, config.py
│  ├─ api/  services/  utils/  logs/
└─ frontend/
   ├─ public/  src/
```
## Project Structure
```
kakaoOrder/
├─ backend/          # FastAPI 백엔드
│  ├─ main.py        # 서버 엔트리포인트
│  ├─ api/           # 라우터, 핸들러, 모델
│  ├─ services/      # 비즈니스 로직
│  ├─ utils/         # 공통 유틸리티
│  ├─ logs/          # 분석 로그 및 스트림 청크
│  └─ config.py      # 환경 설정
├─ frontend/         # React 프론트엔드
│  ├─ public/        # 정적 파일
│  └─ src/           # 컴포넌트 및 스타일
└─ README.md         # 프로젝트 가이드


## 5. Data & Processing Flow
1. 사용자 입력: 채팅방, 날짜 범위, 원시 대화 텍스트  
2. 입력 검증: 비어있음, 날짜 형식  
3. `filter_conversation_by_date`: 날짜 필터링  
4. `preprocess_chat`: 대화 3천자 단위 청크 분할  
5. `analyze_conversation_chunk`: LLM 비동기 호출  
6. `merge_analysis_results`: 청크 결과 병합 및 정규화

## 6. API Endpoints Overview
- **POST** `/api/analyze`: 대화 텍스트 분석 요청 → `AnalysisResponse`  
- **POST** `/api/analyze-file`: 파일 업로드 기반 분석  
- **GET** `/api/result/{job_id}`: 분석 상태 및 결과 조회 → `AnalysisStatusResponse`  
- **POST** `/api/generate-csv`: CSV 생성 → `CSVGenerationResponse`  
- **GET** `/api/jobs`: 작업 목록 조회 (관리자)  
- **GET** `/api/health`: 서버 상태 확인  
## 7. Detailed API Endpoints

### 7.1 POST /api/analyze
- Request (JSON):
  ```json
  {
    "shop_name": "우국상검단점",
    "start_date": "2025-05-01",
    "end_date": "2025-05-07",
    "conversation": "안녕하세요..."
  }
  ```
- Response (200):
  ```json
  {
    "success": true,
    "job_id": "abc123",
    "error": null
  }
  ```
- Background Task: `process_conversation_task` 실행, 비동기 결과 준비

### 7.2 POST /api/analyze-file
- Form Data: `file` (txt), `shop_name`, `start_date`, `end_date`
- Response: 동일한 구조로 `job_id` 반환

### 7.3 GET /api/result/{job_id}
- Response (AnalysisStatusResponse):
  - `status`: "pending" | "completed" | "failed"
  - `result`: 분석 결과 JSON (optional)
  - `error`: 오류 메시지 (optional)

### 7.4 POST /api/generate-csv
- Body: 전체 분석 결과 JSON
- Response: base64 인코딩된 CSV 데이터 또는 파일 URL

---

## 8. Performance & Limitations
- **대화 길이**: 3만자 처리 시 약 30분 소요 (단일 스레드, 직렬 LLM 호출 기준)
- **병렬 처리**: 현재 최대 청크별 비동기 작업만 지원, 전체 병렬화 필요
- **LLM 호출 지연**: Claude API 응답 속도 의존, 네트워크 및 API 레이트 제한 발생
- **I/O 오버헤드**: 로그 저장 및 읽기→쓰기 반복 작업 최적화 필요
- **메모리 사용량**: 대규모 청크 병렬 처리 시 메모리 급증 가능

---
## 9. Areas for Improvement (Consolidated)
1. **병렬 처리 강화**  
   - LLM 호출을 워커 풀 또는 Celery 기반 분산 작업으로 전환  
   - 청크 크기 동적 조절 (GPU/CPU 리소스에 맞춰)
2. **진행 상태 모니터링**  
   - WebSocket으로 실시간 진행률 브로드캐스트  
   - 프론트엔드에서 각 청크별 완료 이벤트 표시
3. **캐싱 및 재시도 로직**  
   - 동일 대화/청크 재요청 시 캐시된 응답 활용  
   - LLM 호출 실패 시 지수 백오프 재시도
4. **API 보안**  절대 안할꺼임 (MVP 테스트 서비스임)
   - CORS 도메인 화이트리스트 적용  
   - JWT 기반 인증 및 역할 기반 권한 관리
5. **로깅 및 에러 관리**  
   - 구조화된 JSON 로그 (e.g., Logstash 호환)  
   - Sentry 연동 등 외부 모니터링 도구 사용 절대 안할꺼임 (MVP 테스트 서비스임)

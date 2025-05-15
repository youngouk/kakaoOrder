# 카카오톡 주문 분석 서비스

카카오톡 대화 내역에서 주문 정보를 자동으로 추출하고 정리해주는 웹 서비스입니다. LLM(Claude 3.7 Sonnet with Thinking)을 활용하여 대화에서 언급된 주문 내역을 시간별, 품목별, 주문자별로 분석합니다.

## 주요 기능

- **카카오톡 대화 내역 분석**: Claude 3.7 Sonnet의 Thinking 기능을 활용한 정확한 분석
- **판매물품 자동 인식**: 판매자 메시지에서 품목, 가격, 마감 정보 자동 추출
- **시간순 주문 내역 정리**: 대화 타임라인에 따른 주문 정보 표시
- **품목별 총 주문 갯수 요약**: 각 품목별 총 주문량 및 주문자 정보
- **주문자별 주문 내역 정리**: 주문자 기준 주문 내용 표시
- **검색 기능**: 모든 주문 데이터 내에서 검색 가능
- **CSV 형식으로 데이터 내보내기**: 타입별 또는 전체 데이터 다운로드
- **비동기 분석 처리**: 대용량 대화 처리 시 백그라운드 작업 처리

## 개선된 사용자 경험

- **직관적인 UI**: 깔끔하고 현대적인 디자인
- **반응형 디자인**: 모바일 및 데스크톱 환경 모두 지원
- **날짜 선택 기능**: 특정 날짜의 대화만 분석 가능
- **실시간 상태 표시**: 분석 진행 상황 확인
- **데이터 필터링**: 검색 기능으로 원하는 정보만 빠르게 확인
- **CSV 내보내기 개선**: UTF-8 인코딩 및 Excel 호환성 강화

## 프로젝트 구조

```text
kakaoOrder/
│
├── backend/          # Python FastAPI 백엔드
│   ├── main.py       # 메인 서버 및 API 엔드포인트
│   ├── config.py     # 환경 변수 및 설정
│   ├── requirements.txt # 백엔드 의존성 목록
│   ├── api/          # FastAPI 라우터 및 핸들러 모듈
│   │   ├── router.py
│   │   ├── handlers.py
│   │   └── models.py
│   ├── services/     # 비즈니스 로직 서비스 모듈
│   │   ├── llm_service.py
│   │   ├── product_service.py
│   │   ├── preprocess_chat.py
│   │   ├── analysis_service.py
│   │   └── export_service.py
│   ├── utils/        # 유틸리티 모듈
│   │   ├── text_processing.py
│   │   ├── validation.py
│   │   └── date_utils.py
│   └── logs/         # 분석 중 생성되는 로그 및 파일
│       ├── preprocessed_texts/
│       ├── claude_responses/
│       ├── fallback_raw_json/
│       ├── stream_chunks/
│       └── fallback_stream_chunks/
└── frontend/         # React.js 프론트엔드
    ├── public/
    │   └── index.html
    ├── src/
    │   ├── App.js
    │   ├── App.css
    │   ├── index.js
    │   └── components/
    │       ├── ChatInput.js
    │       └── ResultDisplay.js
    └── package.json
```

## 핵심 함수 및 처리 흐름

### 주요 함수 설명 (llm_service.py)

1. **extract_product_info_from_seller_messages**
   - 판매자 메시지에서 판매 상품 정보 추출
   - 상품명, 가격, 카테고리, 수령일, 마감 정보 식별

2. **get_available_products**
   - 대화 내용에서 현재 주문 가능한 상품 목록 추출
   - 마감된 상품 제외 및 상품 패턴 식별

3. **is_valid_item_name**
   - 품목명 유효성 검증
   - 날짜, 시간, 닉네임 등 오인식 패턴 필터링
   - 판매 중인 상품 목록과 비교 검증

4. **filter_conversation_by_date**
   - 날짜 기준으로 대화 필터링
   - 시작일/종료일 범위 설정 가능

5. **analyze_conversation**
   - 대화 분석의 시작점
   - 대화 분할 및 병렬 처리 관리
   - 청크별 결과 병합 조정

6. **analyze_conversation_chunk**
   - 단일 대화 청크 분석
   - Claude API 호출 및 결과 처리
   - 판매 상품 정보를 분석 프롬프트에 추가

7. **merge_analysis_results**
   - 여러 청크의 분석 결과 병합
   - 데이터 중복 처리 및 정리
   - 6가지 주요 테이블 구성

8. **extract_orders_directly**
   - API 응답이 실패할 경우, 대화에서 직접 주문 추출
   - 정규식 패턴 매칭으로 주문 정보 식별
   - 추출된 판매 상품 정보 활용

### 데이터 처리 흐름

1. **사용자가 대화 내용 제출**
   - 가게/채팅방 이름, 날짜 범위 지정 가능

2. **전처리 단계**
   - `filter_conversation_by_date`로 날짜 필터링
   - 대화 길이에 따라 청크 분할 여부 결정

3. **판매자 메시지 분석**
   - `extract_product_info_from_seller_messages`로 상품 정보 추출
   - 상품명, 가격, 카테고리, 수령일, 마감 정보 수집

4. **주문 정보 추출**
   - 대화 길이에 따라 단일/병렬 처리 실행
   - 각 청크는 `analyze_conversation_chunk`에서 처리
   - Claude API 또는 직접 추출 방식으로 주문 식별

5. **결과 병합 및 후처리**
   - `merge_analysis_results`로 여러 청크 결과 병합
   - 중복 주문 처리 및 데이터 정규화
   - 6가지 주요 테이블 구성:
     - 판매물품 정의
     - 시간순 주문 내역
     - 품목별 총 주문 갯수
     - 주문자별 주문 내역
     - 주문자-상품 교차표
     - 주문 패턴 분석

6. **결과 반환**
   - 프론트엔드에 JSON 형식으로 결과 전달
   - 테이블 형태로 시각화 및 CSV 내보내기 지원

## 설치 및 실행 방법

### 백엔드 설정

1. Python 3.7 이상 설치
2. 필요한 패키지 설치:
   ```
   cd backend
   pip install -r requirements.txt
   ```
3. `.env` 파일 생성 후 API 키 설정:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   ```
4. 서버 실행:
```bash
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
서버는 기본적으로 http://localhost:8000 에서 실행됩니다.

### 프론트엔드 설정

1. Node.js 설치
2. 필요한 패키지 설치:
   ```
   cd frontend
   npm install
   ```
3. 개발 서버 실행:
   ```
   npm start
   ```
   프론트엔드는 기본적으로 http://localhost:3000 에서 실행됩니다.

## 사용 방법

1. 웹 브라우저에서 http://localhost:3000 접속
2. 가게/채팅방 이름 입력 (기본값: 우국상검단점)
3. 필요시 날짜 선택 (특정 날짜의 대화만 분석하려는 경우)
4. 카카오톡 대화 내역을 텍스트 영역에 붙여넣기
5. '분석 시작' 버튼 클릭
6. 분석이 진행되는 동안 상태 메시지 확인
7. 결과를 확인하고 필요시 검색 기능 사용
8. 원하는 형식으로 CSV 다운로드

## 기능 개선 및 최적화

- **비동기 분석 처리**: 대용량 대화 처리 시 백그라운드에서 작업을 수행하고 주기적으로 결과 확인
- **검색 기능 추가**: 모든 주문 데이터 내에서 키워드 검색 가능
- **UI/UX 개선**: 카카오톡 테마 색상을 활용한 직관적인 디자인
- **반응형 디자인**: 모바일 환경에서도 편리하게 사용 가능
- **폼 유효성 검사**: 입력 데이터 검증 및 오류 방지
- **CSV 인코딩 개선**: 한글 깨짐 방지를 위한 UTF-8 BOM 인코딩 적용
- **작업 상태 관리**: 서버 측에서 작업 상태 추적 및 관리

## API 엔드포인트

- **POST /api/analyze**: 텍스트 대화 분석 요청
- **POST /api/analyze-file**: 업로드된 TXT 파일 분석 요청
- **GET /api/result/{job_id}**: 분석 결과 조회
- **POST /api/generate-csv**: 분석 결과 기반 CSV 생성 (선택적)
- **GET /api/jobs**: 모든 분석 작업 목록 조회 (관리자용)
- **GET /api/health**: 서버 상태 확인

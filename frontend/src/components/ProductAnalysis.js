import React, { useState } from 'react';
import axios from 'axios';
import ResultDisplay from './ResultDisplay';

// API base URL (App.js와 동일하게 가져오기)
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

function ProductAnalysis() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [productNames, setProductNames] = useState('');
  const [conversation, setConversation] = useState('');
  const [shopName, setShopName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const [processingStatus, setProcessingStatus] = useState(null);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // 입력 검증
    if (!conversation) {
      setError("대화 내용을 입력해주세요");
      return;
    }
    
    if (!productNames) {
      setError("조회할 상품명을 입력해주세요");
      return;
    }
    
    // 상품명 목록 변환 (콤마로 구분된 문자열 → 배열)
    const productList = productNames
      .split(',')
      .map(name => name.trim())
      .filter(name => name.length > 0);
      
    if (productList.length === 0) {
      setError("유효한 상품명을 입력해주세요");
      return;
    }
    
    if (productList.length > 20) {
      setError("상품명은 최대 20개까지 입력 가능합니다");
      return;
    }
    
    setIsLoading(true);
    setError(null);
    setResult(null);
    setProcessingStatus('분석 시작');
    
    try {
      // 새 API 엔드포인트 호출
      const response = await axios.post(`${API_BASE_URL}/api/specific/analyze-specific-products`, {
        conversation: conversation,
        product_names: productList,
        shop_name: shopName || null,
        start_date: startDate || null,
        end_date: endDate || null
      });
      
      if (response.data.job_id) {
        checkAnalysisResult(response.data.job_id);
      } else {
        setError("작업 ID를 받지 못했습니다");
        setIsLoading(false);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "분석 요청 중 오류가 발생했습니다");
      setIsLoading(false);
    }
  };
  
  // 결과 확인 함수 (App.js의 checkAnalysisResult와 유사)
  const checkAnalysisResult = async (id) => {
    try {
      setProcessingStatus('분석 중... (약 1-2분 소요)');
      const checkResultInterval = setInterval(async () => {
        try {
          const resultResponse = await axios.get(`${API_BASE_URL}/api/specific/result/${id}`);
          if (resultResponse.data.status === 'completed') {
            clearInterval(checkResultInterval);
            setResult(resultResponse.data.result);
            setIsLoading(false);
            setProcessingStatus('완료');
          } else if (resultResponse.data.status === 'failed') {
            clearInterval(checkResultInterval);
            setError(resultResponse.data.error || '분석 처리 중 오류가 발생했습니다.');
            setIsLoading(false);
            setProcessingStatus('실패');
          } else {
            // 진행 중인 경우 상태 표시
            setProcessingStatus(`분석 중... (${resultResponse.data.status})`);
          }
        } catch (checkErr) {
          clearInterval(checkResultInterval);
          setError('결과 확인 중 오류가 발생했습니다.');
          setIsLoading(false);
          setProcessingStatus('실패');
        }
      }, 3000); // 3초마다 확인
    } catch (err) {
      setError('결과 확인 요청 중 오류가 발생했습니다.');
      setIsLoading(false);
      setProcessingStatus('실패');
    }
  };

  return (
    <div className="product-analysis">
      <h2>개별 상품 분석</h2>
      
      {isLoading && (
        <div className="status-message">
          <div className="loading-spinner"></div>
          <p>상태: {processingStatus}</p>
        </div>
      )}
      
      {error && (
        <div className="error-message">
          <p>오류: {error}</p>
        </div>
      )}
      
      {result ? (
        <>
          <ResultDisplay analysisData={result} isLoading={isLoading} shopName={shopName} />
          <button 
            className="btn btn-primary" 
            onClick={() => {
              setResult(null);
              setProcessingStatus(null);
            }}
          >
            새 분석
          </button>
        </>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="shop-name">가게/채팅방 이름 (선택사항)</label>
            <input
              type="text"
              id="shop-name"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              className="form-control"
              placeholder="예: 우국상검단점, 국민상회 머슴"
            />
          </div>
          
          <div className="form-row">
            <div className="form-group half">
              <label htmlFor="start-date">시작 날짜 및 시간 (선택사항)</label>
              <input
                type="datetime-local"
                id="start-date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="form-control"
              />
            </div>
            <div className="form-group half">
              <label htmlFor="end-date">종료 날짜 및 시간 (선택사항)</label>
              <input
                type="datetime-local"
                id="end-date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="form-control"
              />
            </div>
          </div>
          
          <div className="form-group">
            <label htmlFor="product-names">조회할 상품명 (콤마로 구분, 1-20개)</label>
            <textarea
              id="product-names"
              value={productNames}
              onChange={(e) => setProductNames(e.target.value)}
              className="form-control product-textarea"
              placeholder="분석할 상품명을 정확히 입력하세요. 여러 상품은 쉼표(,)로 구분해주세요.
예시: 한우나주곰탕, 한우사골곰탕, 프리미엄 우삼겹
주의사항: 상품명은 대화에 언급된 정확한 이름과 일치해야 합니다."
              rows={3}
            />
            <small className="text-muted">
              현재 {productNames.split(',').filter(name => name.trim().length > 0).length}개 상품 입력됨
            </small>
          </div>
          
          <div className="form-group">
            <label htmlFor="conversation">대화 내용</label>
            <textarea
              id="conversation"
              value={conversation}
              onChange={(e) => setConversation(e.target.value)}
              className="form-control"
              placeholder="카카오톡 대화 내용을 붙여넣으세요"
              rows={10}
              required
            />
            <small className="text-muted">
              {conversation.length.toLocaleString()}자 입력됨
            </small>
          </div>
          
          <button 
            type="submit" 
            className="btn btn-primary submit-button" 
            disabled={isLoading}
          >
            {isLoading ? '분석 중...' : '상품별 주문 분석하기'}
          </button>
        </form>
      )}
    </div>
  );
}

export default ProductAnalysis; 
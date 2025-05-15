import React, { useState } from 'react';
import axios from 'axios';
import ChatInput from './components/ChatInput';
import ResultDisplay from './components/ResultDisplay';
import './App.css';

// API base URL (deployed backend)
const API_BASE_URL = 'https://overflowing-truth.railway.internal';

function App() {
  const [analysisData, setAnalysisData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [processingStatus, setProcessingStatus] = useState(null);

  const handleSubmit = async (data) => {
    setIsLoading(true);
    setError(null);
    setAnalysisData(null);
    setProcessingStatus('시작됨');
    
    try {
      // 파일 업로드로 이미 요청을 보낸 경우
      if (data.isFileUpload && data.job_id) {
        checkAnalysisResult(data.job_id);
        return;
      }
      
      // 텍스트 입력 방식의 분석 작업 요청
      const response = await axios.post(`${API_BASE_URL}/api/analyze`, {
        conversation: data.conversation,
        start_date: data.start_date || null,
        end_date: data.end_date || null,
        shop_name: data.shop_name || null
      });
      
      if (response.data.success || response.data.job_id) {
        // job_id가 있는 경우 폴링 방식으로 결과 확인
        if (response.data.job_id) {
          checkAnalysisResult(response.data.job_id);
        } else if (response.data.data) {
          // 즉시 결과가 반환된 경우
          setAnalysisData(response.data.data);
          setIsLoading(false);
        }
      } else {
        setError(response.data.error || '분석 중 오류가 발생했습니다.');
        setIsLoading(false);
      }
    } catch (err) {
      setError(err.message || '서버 연결 중 오류가 발생했습니다.');
      setIsLoading(false);
    }
  };

  // 폴링 방식으로 분석 결과 확인
  const checkAnalysisResult = async (id) => {
    try {
      setProcessingStatus('분석 중... (약 1-2분 소요)');
      const checkResultInterval = setInterval(async () => {
        try {
          const resultResponse = await axios.get(`${API_BASE_URL}/api/result/${id}`);
          if (resultResponse.data.status === 'completed') {
            clearInterval(checkResultInterval);
            setAnalysisData(resultResponse.data.result);
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

  const handleNewAnalysis = () => {
    setAnalysisData(null);
    setIsLoading(false);
    setError(null);
    setProcessingStatus(null);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>정보자동 추출/정리</h1>
        <p>대화에서 주문 정보를 자동으로 추출하고 정리해주는 서비스입니다.</p>
      </header>
      
      <main className="app-main">
        {!analysisData ? (
          <>
            <ChatInput onSubmit={handleSubmit} isLoading={isLoading} />
            
            {processingStatus && (
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
          </>
        ) : (
          <>
            <ResultDisplay analysisData={analysisData} shopName={analysisData.shop_name} />
            <div className="action-buttons">
              <button onClick={handleNewAnalysis} className="btn btn-secondary">
                새 분석 시작
              </button>
            </div>
          </>
        )}
      </main>
      
      <footer className="app-footer">
        <p>&copy; 2025 카카오톡 주문 분석</p>
      </footer>
    </div>
  );
}

export default App;
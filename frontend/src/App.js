import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import ChatInput from './components/ChatInput';
import ResultDisplay from './components/ResultDisplay';
import ProductAnalysis from './components/ProductAnalysis';
import ProgressLog from './components/ProgressLog';
import './App.css';

// API base URL configurable via environment variable
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [startTime, setStartTime] = useState(null);
  const [elapsedTime, setElapsedTime] = useState('00:00');
  const elapsedTimerRef = useRef(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [processingStatus, setProcessingStatus] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [progressLogs, setProgressLogs] = useState([]);

  const handleSubmit = async (data) => {
    setIsLoading(true);
    setStartTime(Date.now());
    setElapsedTime('00:00');
    setError(null);
    setAnalysisData(null);
    setProcessingStatus('시작됨');
    setProgressLogs([]);
    
    addProgressLog({
      phase: '분석 시작',
      details: [
        `상점명: ${data.shop_name || '미지정'}`,
        `분석 기간: ${data.start_date || '전체'} ~ ${data.end_date || '전체'}`
      ]
    });
    
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
          
          addProgressLog({
            phase: '분석 결과 종합 및 완료',
            details: [
              '모든 대화 분석 결과 병합 완료.',
              `최종 집계: 시간 기반 주문 총 ${response.data.data.time_based_orders?.length || 0}개, ` +
              `고객 기반 주문 총 ${response.data.data.customer_based_orders?.length || 0}개, ` +
              `품목별 요약 ${response.data.data.item_based_summary?.length || 0}개`,
              '분석 결과 저장 완료.'
            ]
          });
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

  const addProgressLog = (log) => {
    setProgressLogs(prevLogs => [...prevLogs, {
      ...log,
      timestamp: new Date().toLocaleTimeString('ko-KR')
    }]);
  };

  const checkAnalysisResult = async (id) => {
    try {
      setProcessingStatus('분석 중... (약 1-2분 소요)');
      
      addProgressLog({
        phase: '데이터 로딩 및 초기 처리',
        details: ['분석 작업이 서버에서 처리 중입니다...']
      });
      
      const checkResultInterval = setInterval(async () => {
        try {
          const resultResponse = await axios.get(`${API_BASE_URL}/api/result/${id}`);
          
          if (resultResponse.data.status === 'completed') {
            clearInterval(checkResultInterval);
            setAnalysisData(resultResponse.data.result);
            setIsLoading(false);
            setProcessingStatus('완료');
            
            // 서버에서 받은 진행상태 로그가 있으면 그대로 사용 (타임스탬프 변경 안함)
            if (resultResponse.data.progress_logs && Array.isArray(resultResponse.data.progress_logs)) {
              setProgressLogs(resultResponse.data.progress_logs);
            }
            
          } else if (resultResponse.data.status === 'failed') {
            clearInterval(checkResultInterval);
            setError(resultResponse.data.error || '분석 처리 중 오류가 발생했습니다.');
            setIsLoading(false);
            setProcessingStatus('실패');
            
            // 실패 시에도 진행상태 로그가 있으면 그대로 사용
            if (resultResponse.data.progress_logs && Array.isArray(resultResponse.data.progress_logs)) {
              setProgressLogs(resultResponse.data.progress_logs);
            }
            
          } else {
            setProcessingStatus(`분석 중... (${resultResponse.data.status})`);
            
            // 서버에서 받은 진행상태 로그 업데이트 (타임스탬프 보존)
            if (resultResponse.data.progress_logs && Array.isArray(resultResponse.data.progress_logs)) {
              // 중복 로그 제거하면서 업데이트 (서버 로그 우선)
              setProgressLogs(prevLogs => {
                // 기존 클라이언트 생성 로그와 서버 로그 구분
                const clientLogs = prevLogs.filter(log => 
                  log.phase === '데이터 로딩 및 초기 처리' || 
                  log.phase === '분석 시작' ||
                  log.phase === '오류 발생'
                );
                
                // 서버 로그가 있으면 서버 로그만 사용, 없으면 클라이언트 로그 유지
                if (resultResponse.data.progress_logs.length > 0) {
                  return resultResponse.data.progress_logs;
                } else {
                  return clientLogs;
                }
              });
            }
          }
        } catch (checkErr) {
          clearInterval(checkResultInterval);
          setError('결과 확인 중 오류가 발생했습니다.');
          setIsLoading(false);
          setProcessingStatus('실패');
          
          addProgressLog({
            phase: '오류 발생',
            details: ['결과 확인 중 오류가 발생했습니다.']
          });
        }
      }, 3000);
    } catch (err) {
      setError('결과 확인 요청 중 오류가 발생했습니다.');
      setIsLoading(false);
      setProcessingStatus('실패');
      
      addProgressLog({
        phase: '오류 발생',
        details: ['결과 확인 요청 중 오류가 발생했습니다.']
      });
    }
  };



  useEffect(() => {
    if (startTime && isLoading) {
      elapsedTimerRef.current = setInterval(() => {
        const diff = Date.now() - startTime;
        const minutes = String(Math.floor(diff / 60000)).padStart(2, '0');
        const seconds = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');
        setElapsedTime(`${minutes}:${seconds}`);
      }, 1000);
    }
    return () => clearInterval(elapsedTimerRef.current);
  }, [startTime, isLoading]);

  const handleNewAnalysis = () => {
    setAnalysisData(null);
    setIsLoading(false);
    setError(null);
    setProcessingStatus(null);
    setStartTime(null);
    setElapsedTime('00:00');
    setProgressLogs([]);
  };

  return (
    <div className="App">
      <header className="app-header">
        <h1>카카오톡 주문 분석</h1>
        <p>대화 내용에서 주문 정보를 자동으로 추출하고 분석해주는 서비스</p>
      </header>
      <div className="tabs">
        <button className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>대화 내용 입력</button>
        <button className={`tab-button ${activeTab === 'product' ? 'active' : ''}`} onClick={() => setActiveTab('product')}>개별 상품 분석</button>
      </div>
      <div className="tab-content">
        {activeTab === 'chat' && (
          <>
            {!analysisData ? (
              <>
                <ChatInput onSubmit={handleSubmit} isLoading={isLoading} />

                {processingStatus && (
                  <div className="status-message">
                    <div className="loading-spinner"></div>
                    <p>상태: {processingStatus}</p>
                    <p>소요 시간: {elapsedTime}</p>
                  </div>
                )}
                
                {progressLogs.length > 0 && (
                  <ProgressLog logs={progressLogs} />
                )}

                {error && (
                  <div className="error-message">
                    <p>오류: {error}</p>
                  </div>
                )}
              </>
            ) : (
              <ResultDisplay 
                analysisData={analysisData} 
                isLoading={isLoading} 
                analysisTime={elapsedTime}
                onBackToMain={handleNewAnalysis}
                progressLogs={progressLogs}
              />
            )}
          </>
        )}
        {activeTab === 'product' && <ProductAnalysis />}
      </div>
      
      <footer className="app-footer">
        <p>&copy; 2025 카카오톡 주문 분석</p>
      </footer>
    </div>
  );
}

export default App;
import React, { useState, useRef, useEffect } from 'react';

function ProgressLog({ logs, isComplete = false }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const logEndRef = useRef(null);
  
  // 로그가 추가될 때마다 스크롤을 맨 아래로 이동
  useEffect(() => {
    if (isExpanded && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isExpanded]);
  
  if (!logs || logs.length === 0) return null;
  
  // 안전한 타임스탬프 파싱
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return new Date().toLocaleTimeString('ko-KR');
    
    try {
      // ISO 형식 (백엔드에서 생성)
      if (typeof timestamp === 'string' && timestamp.includes('T')) {
        return new Date(timestamp).toLocaleTimeString('ko-KR');
      }
      // 이미 한국어 시간 형식인 경우
      if (typeof timestamp === 'string' && timestamp.includes(':')) {
        return timestamp;
      }
      // 기타 형식
      return new Date(timestamp).toLocaleTimeString('ko-KR');
    } catch (error) {
      console.warn('타임스탬프 파싱 오류:', timestamp, error);
      return new Date().toLocaleTimeString('ko-KR');
    }
  };
  
  // 로그에서 상점명과 분석 기간 추출
  const extractAnalysisInfo = () => {
    const analysisStartLog = logs.find(log => log.phase === '분석 시작');
    if (!analysisStartLog || !analysisStartLog.details) {
      return {
        shopName: '미지정',
        period: '전체 ~ 전체'
      };
    }
    
    let shopName = '미지정';
    let period = '전체 ~ 전체';
    
    analysisStartLog.details.forEach(detail => {
      if (detail.includes('상점명:')) {
        shopName = detail.split('상점명:')[1]?.trim() || '미지정';
      }
      if (detail.includes('분석 기간:')) {
        period = detail.split('분석 기간:')[1]?.trim() || '전체 ~ 전체';
      }
    });
    
    return { shopName, period };
  };
  
  const analysisInfo = extractAnalysisInfo();
  
  // 주요 단계별 아이콘 매핑
  const getPhaseIcon = (phase) => {
    if (phase.includes('전처리')) return '🧹';
    if (phase.includes('주문가능 품목')) return '📦';
    if (phase.includes('메인 분석') && phase.includes('시작')) return '🚀';
    if (phase.includes('경과')) return '⏱️';
    if (phase.includes('응답 수신')) return '📨';
    if (phase.includes('기타 정보 생성 완료')) return '✅';
    if (phase.includes('시작')) return '🚀';
    if (phase.includes('필터링')) return '🔍';
    if (phase.includes('통계') || phase.includes('분석 완료')) return '📊';
    if (phase.includes('분할') || phase.includes('청크')) return '✂️';
    if (phase.includes('완료')) return '✅';
    if (phase.includes('오류') || phase.includes('실패')) return '❌';
    if (phase.includes('로딩') || phase.includes('처리')) return '⚙️';
    return '📋';
  };
  
  // 진행률 계산 개선 - 새로운 10단계 시스템 지원
  const calculateProgress = () => {
    if (isComplete) return 100;
    
    // 백엔드에서 직접 전달되는 progress 값 확인
    const latestLog = logs[logs.length - 1];
    if (latestLog && latestLog.progress !== undefined) {
      return latestLog.progress;
    }
    
    // 폴백: 단계별 진행률 계산
    const progressMap = {
      '대화내용 전처리 완료': 10,
      '주문가능 품목 분석 요청 시작': 15,
      '주문가능 품목 응답 받음': 25,
      '메인 분석(timebase)을 위한 LLM 호출 시작': 30,
      '메인 분석을 위한 LLM 호출 시작 후 60초 경과': 40,
      '메인 분석을 위한 LLM 호출 시작 후 240초 경과': 50,
      '메인 분석을 위한 LLM 호출 시작 후 480초 경과': 70,
      '메인 분석을 위한 LLM 호출 시작 후 600초 경과': 85,
      '메인 분석 응답 수신': 95,
      '메인 분석 바탕으로 주문자별 정보 등 기타 정보 생성 완료': 100
    };
    
    let maxProgress = 0;
    logs.forEach(log => {
      const phaseProgress = progressMap[log.phase];
      if (phaseProgress) {
        maxProgress = Math.max(maxProgress, phaseProgress);
      }
    });
    
    // 최소 진행률 보장 (로그가 있으면 최소 5%)
    if (maxProgress === 0 && logs.length > 0) {
      return 5;
    }
    
    return maxProgress;
  };
  
  const progress = calculateProgress();
  
  return (
    <div className="progress-log-container">
      <div className="progress-log-header" onClick={() => setIsExpanded(!isExpanded)}>
        <h3>
          분석 진행 상태 
          <span className="progress-indicator">({progress}% 완료)</span>
          {isExpanded ? ' ▼' : ' ▶'}
        </h3>
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      {isExpanded && (
        <div className="progress-log-content">
          {/* 분석 요약 정보 표시 */}
          {analysisInfo.shopName !== '미지정' && (
            <div className="analysis-summary">
              <div className="summary-item">
                <strong>🏪 상점명:</strong> {analysisInfo.shopName}
              </div>
              <div className="summary-item">
                <strong>📅 분석 기간:</strong> {analysisInfo.period}
              </div>
            </div>
          )}
          
          {logs.map((log, index) => (
            <div key={`log-${index}`} className="log-entry">
              <div className="log-phase">
                <span className="log-icon">{getPhaseIcon(log.phase)}</span>
                <span className="log-timestamp">
                  [{formatTimestamp(log.timestamp)}]
                </span>
                <span className="log-phase-title">{log.phase}</span>
              </div>
              
              {log.details && log.details.length > 0 && (
                <ul className="log-details">
                  {log.details.map((detail, detailIndex) => (
                    <li key={`detail-${index}-${detailIndex}`}>
                      {detail.includes('소요될 수 있습니다') ? (
                        <span className="analysis-notice">{detail}</span>
                      ) : (
                        detail
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  );
}

export default ProgressLog; 
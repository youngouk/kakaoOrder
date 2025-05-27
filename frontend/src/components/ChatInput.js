import React, { useState, useRef } from 'react';
import axios from 'axios';
// API base URL configurable via environment variable
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

function ChatInput({ onSubmit, isLoading }) {
  const [conversation, setConversation] = useState('');
  const [shopName, setShopName] = useState('우국상검단점');
  const [inputMethod, setInputMethod] = useState('file'); // 'text' 또는 'file'
  const [file, setFile] = useState(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // 오늘 날짜를 시작 00:00, 종료 23:59로 초기 설정하는 헬퍼 함수
  const getTodayDefault = (hour, minute) => {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const hh = String(hour).padStart(2, '0');
    const mi = String(minute).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
  };

  const [startDate, setStartDate] = useState(() => getTodayDefault(0, 0));
  const [endDate, setEndDate] = useState(() => getTodayDefault(23, 59));

  // 포맷에 맞는 날짜 변환 함수
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const pad = (num) => num.toString().padStart(2, '0');
    const year = date.getFullYear();
    const month = pad(date.getMonth() + 1);
    const day = pad(date.getDate());
    const hours = pad(date.getHours());
    const minutes = pad(date.getMinutes());
    const seconds = pad(date.getSeconds());
    return `${year}년 ${month}월 ${day}일 ${hours}시 ${minutes}분 ${seconds}초`;
  };

  const handleStartDateChange = (e) => {
    setStartDate(e.target.value);
  };

  const handleEndDateChange = (e) => {
    setEndDate(e.target.value);
  };

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      // 파일 확장자 확인
      if (selectedFile.name.endsWith('.txt') || selectedFile.type === 'text/plain') {
        setFile(selectedFile);
      } else {
        alert('TXT 파일만 업로드 가능합니다.');
        e.target.value = '';
        setFile(null);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (inputMethod === 'text' && !conversation.trim()) {
      alert('대화 내용을 입력해주세요.');
      return;
    }
    
    if (inputMethod === 'file' && !file) {
      alert('TXT 파일을 업로드해주세요.');
      return;
    }
    
    // 텍스트 입력 방식일 경우
    if (inputMethod === 'text') {
      onSubmit({
        conversation,
        start_date: formatDate(startDate),
        end_date: formatDate(endDate),
        shop_name: shopName
      });
    } 
    // 파일 업로드 방식일 경우
    else {
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('shop_name', shopName);
        
        if (startDate) {
          formData.append('start_date', formatDate(startDate));
        }
        
        if (endDate) {
          formData.append('end_date', formatDate(endDate));
        }
        
        // API 요청 보내기
        const apiUrl = `${API_BASE_URL}/api/analyze-file`;
        console.log('파일 업로드 요청:', apiUrl);
        
        const response = await axios.post(apiUrl, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            'Accept': 'application/json'
          }
        });
        
        console.log('파일 업로드 응답:', response.data);
        
        if (response.data.success && response.data.job_id) {
          onSubmit({
            job_id: response.data.job_id,
            isFileUpload: true,
            shop_name: shopName,
            start_date: formatDate(startDate),
            end_date: formatDate(endDate)
          });
        } else {
          alert(response.data.error || '파일 업로드 중 오류가 발생했습니다.');
        }
      } catch (error) {
        console.error('파일 업로드 오류:', error);
        alert('파일 업로드 중 오류가 발생했습니다: ' + (error.response?.data?.error || error.message || '알 수 없는 오류'));
      }
    }
  };

  // 텍스트 영역 높이 자동 조절
  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  return (
    <div className="chat-input">
      <h2>대화 내용 입력</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group half">
            <label htmlFor="shop-name">가게/채팅방 이름</label>
            <input
              type="text"
              id="shop-name"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              placeholder="예: 우국상검단점"
              className="form-control"
            />
          </div>
        </div>
        
        <div className="form-row">
          <div className="form-group half">
            <label htmlFor="start-date">시작 날짜 및 시간 (선택사항)</label>
            <input
              type="datetime-local"
              id="start-date"
              value={startDate}
              onChange={handleStartDateChange}
              className="form-control"
            />
          </div>
          <div className="form-group half">
            <label htmlFor="end-date">종료 날짜 및 시간 (선택사항)</label>
            <input
              type="datetime-local"
              id="end-date"
              value={endDate}
              onChange={handleEndDateChange}
              className="form-control"
            />
          </div>
        </div>
        
        <div className="form-group">
          <label>입력 방식</label>
          <div className="input-method-select">
            <label className={`method-option ${inputMethod === 'file' ? 'selected' : ''}`}>
              <input
                type="radio"
                name="inputMethod"
                value="file"
                checked={inputMethod === 'file'}
                onChange={() => setInputMethod('file')}
              />
              <span>TXT 파일 업로드</span>
            </label>
            <label className={`method-option ${inputMethod === 'text' ? 'selected' : ''}`}>
              <input
                type="radio"
                name="inputMethod"
                value="text"
                checked={inputMethod === 'text'}
                onChange={() => setInputMethod('text')}
              />
              <span>텍스트 붙여넣기</span>
            </label>
          </div>
        </div>
        
        {inputMethod === 'text' ? (
          <div className="form-group">
            <label htmlFor="conversation">
              대화 내용 (최대 50,000자)
              <span className="char-count">{conversation.length}/50000</span>
            </label>
            <textarea
              ref={textareaRef}
              id="conversation"
              value={conversation}
              onChange={(e) => {
                setConversation(e.target.value);
                adjustTextareaHeight();
              }}
              onInput={adjustTextareaHeight}
              placeholder="카카오톡 대화 내용을 복사해서 붙여넣으세요..."
              maxLength={50000}
              className="form-control"
              required={inputMethod === 'text'}
            />
          </div>
        ) : (
          <div className="form-group">
            <label htmlFor="file-upload">TXT 파일 업로드</label>
            <input
              ref={fileInputRef}
              type="file"
              id="file-upload"
              accept=".txt"
              onChange={handleFileChange}
              className="form-control"
              required={inputMethod === 'file'}
            />
            {file && (
              <div className="file-info">
                <span>선택된 파일: {file.name}</span>
                <button 
                  type="button" 
                  className="btn-clear-file"
                  onClick={() => {
                    setFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = '';
                  }}
                >
                  취소
                </button>
              </div>
            )}
          </div>
        )}
        
        <div className="instructions">
          <p><strong>사용 팁:</strong></p>
          <ul>
            {inputMethod === 'file' ? (
              <>
                <li>카카오톡 대화방에서 대화 내용을 TXT 파일로 저장합니다.</li>
                <li>저장한 TXT 파일을 업로드해주세요 (UTF-8 인코딩 권장).</li>
              </>
            ) : (
              <>
                <li>카카오톡 대화방에서 분석하려는 대화 내용을 전체 선택합니다.</li>
                <li>복사(Ctrl+C 또는 Cmd+C)한 후 위 텍스트 영역에 붙여넣기(Ctrl+V 또는 Cmd+V)합니다.</li>
              </>
            )}
            <li>시작일과 종료일을 지정하면 해당 기간의 대화만 분석합니다. 2일 이상의 대화 분석은 어렵습니다.</li>
            <li>분석에는 최대 30분이 소요될 수 있습니다.</li>
          </ul>
        </div>
        {/* 
          버튼 스타일 및 배경색, 테두리, 그림자 등은 이미지의 실제 UI와 최대한 유사하게 조정하였습니다.
          - 배경색: 비활성화 시 #f2f2f2, 활성화 시 #f7faff (연한 파랑)
          - 글자색: 비활성화 시 #bdbdbd, 활성화 시 #3a3a3a
          - 테두리: 없음, 둥근 모서리(30px)
          - 그림자: 없음 (이미지 참고)
          - 크기: minWidth 220px, padding 1.1rem 0, 폰트 1.1rem, bold
          - 커서: not-allowed/포인터
          - transition: 부드러운 색상 변화
        */}
        <button
          type="submit"
          className="submit-button enhanced-large-btn"
          disabled={isLoading || (inputMethod === 'text' && !conversation.trim()) || (inputMethod === 'file' && !file)}
          style={{
            padding: '1.1rem 0',
            minWidth: '220px',
            width: '100%',
            fontSize: '1.1rem',
            borderRadius: '30px',
            background: isLoading || (inputMethod === 'text' && !conversation.trim()) || (inputMethod === 'file' && !file)
              ? '#f2f2f2'
              : '#f7faff',
            color: isLoading || (inputMethod === 'text' && !conversation.trim()) || (inputMethod === 'file' && !file)
              ? '#bdbdbd'
              : '#3a3a3a',
            border: 'none',
            fontWeight: 700,
            letterSpacing: '0.01em',
            cursor: isLoading || (inputMethod === 'text' && !conversation.trim()) || (inputMethod === 'file' && !file)
              ? 'not-allowed'
              : 'pointer',
            transition: 'background 0.2s, color 0.2s'
          }}
        >
          {isLoading ? '분석 중...' : '분석 시작'}
        </button>
      </form>
    </div>
  );
}

export default ChatInput;
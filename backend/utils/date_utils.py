import re
from datetime import datetime
from typing import Optional, Tuple

def parse_korean_date(date_str: Optional[str]) -> Optional[str]:
    """
    "YYYY년 MM월 DD일" 형식을 "YYYY-MM-DD" 형식으로 변환합니다.
    
    Args:
        date_str: 한국어 날짜 문자열 (예: "2023년 5월 1일")
        
    Returns:
        ISO 형식의 날짜 문자열 또는 None
    """
    if not date_str:
        return None
        
    # 정규식으로 연, 월, 일 추출
    match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', date_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    
    return None

def format_date_for_display(date_str: str) -> str:
    """
    ISO 형식 날짜(YYYY-MM-DD)를 표시용 형식(YYYY년 MM월 DD일)으로 변환합니다.
    
    Args:
        date_str: ISO 형식 날짜 문자열
        
    Returns:
        표시용 날짜 문자열
    """
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{date_obj.year}년 {date_obj.month}월 {date_obj.day}일"
    except:
        return date_str
        
def is_date_in_range(date_str: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    """
    주어진 날짜가 시작일과 종료일 사이에 있는지 확인합니다.
    
    Args:
        date_str: 확인할 날짜 문자열 (ISO 형식)
        start_date: 시작일 (ISO 형식), None이면 제한 없음
        end_date: 종료일 (ISO 형식), None이면 제한 없음
        
    Returns:
        날짜가 범위 내에 있으면 True, 아니면 False
    """
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            if date < start:
                return False
                
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if date > end:
                return False
                
        return True
    except:
        return False

def extract_timestamp_from_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    """
    메시지 라인에서 날짜와 시간 정보를 추출합니다.
    
    Args:
        line: 메시지 라인
        
    Returns:
        (날짜, 시간) 튜플 (둘 다 ISO 형식)
    """
    date = None
    time = None
    
    # 날짜 추출 (YYYY년 MM월 DD일)
    date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', line)
    if date_match:
        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))
        date = f"{year}-{month:02d}-{day:02d}"
    
    # 시간 추출 (HH:MM 오전/오후)
    time_match = re.search(r'(\d{1,2}):(\d{2})\s*(오전|오후)?', line)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        ampm = time_match.group(3) if time_match.group(3) else ""
        
        if ampm == "오후" and hour < 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
            
        time = f"{hour:02d}:{minute:02d}"
    
    return date, time

def get_today_date_string() -> str:
    """
    오늘 날짜를 ISO 형식(YYYY-MM-DD)으로 반환합니다.
    
    Returns:
        오늘 날짜 문자열
    """
    return datetime.now().strftime("%Y-%m-%d")

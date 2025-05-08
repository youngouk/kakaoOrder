import re
from typing import List, Dict, Set
from config import SELLER_KEYWORDS

def filter_conversation_by_date(conversation_text: str, start_date: str = None, end_date: str = None) -> str:
    """
    날짜 범위에 따라 대화 내용을 필터링합니다.
    
    Args:
        conversation_text: 전체 대화 내용
        start_date: 시작일 (ISO 형식 또는 'YYYY년 MM월 DD일' 형식), None이면 제한 없음
        end_date: 종료일 (ISO 형식 또는 'YYYY년 MM월 DD일' 형식), None이면 제한 없음
        
    Returns:
        필터링된 대화 내용
    """
    from utils.date_utils import parse_korean_date
    
    # 필터링할 날짜가 없으면 원본 반환
    if not start_date and not end_date:
        return conversation_text
    
    # 디버깅용 로그
    print(f"날짜 필터링 시작: start_date={start_date}, end_date={end_date}")
    
    # 한국어 날짜를 ISO 형식으로 변환
    if start_date and "년" in start_date:
        iso_start_date = parse_korean_date(start_date)
        print(f"한국어 날짜 변환: {start_date} -> {iso_start_date}")
        start_date = iso_start_date
    
    if end_date and "년" in end_date:
        iso_end_date = parse_korean_date(end_date)
        print(f"한국어 날짜 변환: {end_date} -> {iso_end_date}")
        end_date = iso_end_date
    
    # 날짜 필터링을 위한 패턴
    # 1. 카카오톡 날짜 구분선
    date_pattern1 = r'--------------- (\d{4})년 (\d{1,2})월 (\d{1,2})일 ---------------'
    # 2. 메시지 라인의 날짜 형식
    date_pattern2 = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(?:오전|오후)'
    
    lines = conversation_text.split('\n')
    filtered_lines = []
    
    include_lines = True
    current_date = None
    
    for line in lines:
        # 1. 날짜 구분선 확인
        date_match = re.search(date_pattern1, line)
        if not date_match:
            # 2. 메시지 라인에서 날짜 추출 시도
            date_match = re.search(date_pattern2, line)
        
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            current_date = f"{year}-{month:02d}-{day:02d}"
            
            # 날짜 범위 체크
            include_lines = True
            if start_date and current_date < start_date:
                include_lines = False
            if end_date and current_date > end_date:
                include_lines = False
                    
        if include_lines:
            filtered_lines.append(line)
    
    # 필터링된 내용이 없으면 안내 메시지 반환
    if not filtered_lines:
        return "지정된 날짜 범위에 해당하는 대화가 없습니다."
    
    filtered_text = '\n'.join(filtered_lines)
    print(f"필터링 전 라인 수: {len(lines)}, 필터링 후 라인 수: {len(filtered_lines)}")
    
    return filtered_text

def split_conversation_into_chunks(conversation_text: str, chunk_size: int = 32000) -> List[str]:
    """
    긴 대화를 처리하기 쉬운 청크로 분할합니다.
    
    Args:
        conversation_text: 전체 대화 내용
        chunk_size: 각 청크의 최대 크기(문자 수)
        
    Returns:
        대화 청크 리스트
    """
    chunks = []
    current_chunk = ""
    current_size = 0
    
    # 날짜 구분선 패턴
    date_pattern = r'--------------- \d{4}년 \d{1,2}월 \d{1,2}일 ---------------'
    
    # 날짜별로 분할
    date_blocks = re.split(f"({date_pattern})", conversation_text)
    
    i = 0
    while i < len(date_blocks):
        # 날짜 구분선이 있는 경우
        if i < len(date_blocks) - 1 and re.match(date_pattern, date_blocks[i]):
            date_line = date_blocks[i]
            content = date_blocks[i+1] if i+1 < len(date_blocks) else ""
            block = date_line + content
            i += 2
        else:
            # 날짜 구분선이 없는 경우
            block = date_blocks[i]
            i += 1
        
        block_size = len(block)
        
        # 블록이 너무 크면 라인 단위로 추가 분할
        if block_size > chunk_size:
            lines = block.split('\n')
            temp_chunk = ""
            for line in lines:
                line_size = len(line) + 1  # +1 for newline
                if len(temp_chunk) + line_size > chunk_size:
                    chunks.append(temp_chunk)
                    temp_chunk = line + '\n'
                else:
                    temp_chunk += line + '\n'
            
            if temp_chunk:
                if current_size + len(temp_chunk) <= chunk_size:
                    current_chunk += temp_chunk
                    current_size += len(temp_chunk)
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = temp_chunk
                    current_size = len(temp_chunk)
        else:
            # 블록이 청크 크기보다 작으면 현재 청크에 추가
            if current_size + block_size <= chunk_size:
                current_chunk += block
                current_size += block_size
            else:
                # 현재 청크를 저장하고 새 청크 시작
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = block
                current_size = block_size
    
    # 마지막 청크 추가
    if current_chunk:
        chunks.append(current_chunk)
    
    # 청크 크기 로깅
    for i, chunk in enumerate(chunks):
        print(f"청크 {i+1} 크기: {len(chunk)} 문자")
        print(f"청크 {i+1} 내용 미리보기: {chunk[:100]}...")
    
    return chunks

def is_seller_message(message_line: str) -> bool:
    """
    메시지가 판매자의 메시지인지 확인합니다.
    
    Args:
        message_line: 메시지 라인
        
    Returns:
        판매자 메시지이면 True, 아니면 False
    """
    for keyword in SELLER_KEYWORDS:
        if keyword in message_line:
            return True
    return False

def clean_text(text: str) -> str:
    """
    텍스트를 정리합니다 (불필요한 공백 제거 등).
    
    Args:
        text: 정리할 텍스트
        
    Returns:
        정리된 텍스트
    """
    if not text:
        return ""
    
    # 공백 정규화
    text = re.sub(r'\s+', ' ', text.strip())
    
    # 특수 기호 정리
    text = text.replace('\u200b', '')  # 제로 폭 공백 제거
    
    return text

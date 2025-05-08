import re
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChatPreprocessor:
    """
    카카오톡 채팅 내용을 전처리하여 분석에 불필요한 메시지를 제거하는 클래스
    """
    
    def __init__(self):
        # 1. 입장 메시지 패턴
        self.enter_pattern = r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2},\s+.+님이\s+들어왔습니다\.'
        
        # 2. 퇴장 메시지 패턴
        self.exit_pattern = r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2},\s+.+님이\s+나갔습니다\.'
        
        # 3. 삭제된 메시지 패턴
        self.deleted_pattern = r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2},\s+.+\s+:\s+삭제된\s+메시지입니다\.'
        
        # 4. 봇 메시지 패턴
        self.bot_pattern = r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2},\s+오픈채팅봇\s+:\s+.+'
        
        # 5. 미디어 메시지 패턴 (사진, 동영상, 이모티콘)
        self.media_pattern = r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2},\s+.+\s+:\s+(?:사진(?:\s+\d+장)?|동영상|이모티콘)'
        
        # 6. 날짜 구분선 패턴 (타임스탬프만 있는 줄)
        self.date_only_pattern = r'^\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+(?:오전|오후)\s+\d{1,2}:\d{2}$'
        
        # 모든 패턴을 하나로 결합 (OR 연산)
        self.all_patterns = '|'.join([
            self.enter_pattern,
            self.exit_pattern,
            self.deleted_pattern,
            self.bot_pattern,
            self.media_pattern,
            self.date_only_pattern
        ])
        
        # 컴파일된 정규식 (성능 향상을 위해)
        self.compiled_pattern = re.compile(self.all_patterns)
        
    def is_unnecessary_message(self, message):
        """
        메시지가 분석에 불필요한 메시지인지 확인
        
        Args:
            message (str): 확인할 메시지 줄
            
        Returns:
            bool: 불필요한 메시지이면 True, 아니면 False
        """
        return bool(self.compiled_pattern.match(message))
    
    def remove_unnecessary_messages(self, chat_text):
        """
        채팅 텍스트에서 불필요한 메시지를 모두 제거
        
        Args:
            chat_text (str): 처리할 채팅 텍스트
            
        Returns:
            str: 불필요한 메시지가 제거된 채팅 텍스트
        """
        lines = chat_text.split('\n')
        filtered_lines = []
        removed_count = 0
        
        for line in lines:
            if line.strip() and not self.is_unnecessary_message(line):
                filtered_lines.append(line)
            else:
                removed_count += 1
        
        logger.info(f"전체 {len(lines)}줄 중 {removed_count}줄 제거됨 ({removed_count/len(lines)*100:.1f}%)")
        
        return '\n'.join(filtered_lines)
    
    def preprocess_chat(self, chat_text):
        """
        채팅 텍스트를 전처리
        
        Args:
            chat_text (str): 원본 채팅 텍스트
            
        Returns:
            str: 전처리된 채팅 텍스트
        """
        # 1. 불필요한 메시지 제거
        cleaned_text = self.remove_unnecessary_messages(chat_text)
        
        # 2. 연속된 빈 줄 제거
        cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
        
        # 3. 텍스트 앞뒤 공백 제거
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text
    
    def get_statistics(self, chat_text):
        """
        채팅 텍스트에서 각 유형별 불필요한 메시지 수를 계산
        
        Args:
            chat_text (str): 채팅 텍스트
            
        Returns:
            dict: 각 유형별 불필요한 메시지 수
        """
        lines = chat_text.split('\n')
        stats = {
            '입장 메시지': 0,
            '퇴장 메시지': 0,
            '삭제된 메시지': 0,
            '봇 메시지': 0,
            '미디어 메시지': 0,
            '날짜 구분선': 0,
            '전체 메시지': len(lines)
        }
        
        for line in lines:
            if re.match(self.enter_pattern, line):
                stats['입장 메시지'] += 1
            elif re.match(self.exit_pattern, line):
                stats['퇴장 메시지'] += 1
            elif re.match(self.deleted_pattern, line):
                stats['삭제된 메시지'] += 1
            elif re.match(self.bot_pattern, line):
                stats['봇 메시지'] += 1
            elif re.match(self.media_pattern, line):
                stats['미디어 메시지'] += 1
            elif re.match(self.date_only_pattern, line):
                stats['날짜 구분선'] += 1
        
        return stats

# 사용 예시 함수
def clean_chat(chat_text):
    """
    채팅 텍스트를 간편하게 정제하는 함수
    
    Args:
        chat_text (str): 원본 채팅 텍스트
        
    Returns:
        str: 정제된 채팅 텍스트
    """
    preprocessor = ChatPreprocessor()
    stats = preprocessor.get_statistics(chat_text)
    
    # 통계 출력
    logger.info("채팅 통계:")
    logger.info(f"  - 전체 메시지: {stats['전체 메시지']}줄")
    logger.info(f"  - 입장 메시지: {stats['입장 메시지']}줄")
    logger.info(f"  - 퇴장 메시지: {stats['퇴장 메시지']}줄")
    logger.info(f"  - 삭제된 메시지: {stats['삭제된 메시지']}줄")
    logger.info(f"  - 봇 메시지: {stats['봇 메시지']}줄")
    logger.info(f"  - 미디어 메시지: {stats['미디어 메시지']}줄")
    logger.info(f"  - 날짜 구분선: {stats['날짜 구분선']}줄")
    
    # 채팅 정제
    cleaned_text = preprocessor.preprocess_chat(chat_text)
    
    # 제거된 메시지 수 계산
    removed_count = stats['입장 메시지'] + stats['퇴장 메시지'] + stats['삭제된 메시지'] + \
                    stats['봇 메시지'] + stats['미디어 메시지'] + stats['날짜 구분선']
    logger.info(f"총 {removed_count}줄 제거됨 ({removed_count/stats['전체 메시지']*100:.1f}%)")
    
    return cleaned_text
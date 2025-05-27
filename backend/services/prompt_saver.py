import pathlib
from datetime import datetime
from typing import Optional

def save_final_prompt_to_file(system_prompt: str, user_prompt: str, shop_name: Optional[str] = None) -> str:
    """
    LLM에 최종 전달되는 전체 프롬프트를 파일로 저장합니다.
    
    Args:
        system_prompt (str): 시스템 프롬프트
        user_prompt (str): 사용자 프롬프트 (preprocessed_text 포함)
        shop_name (str, optional): 상점 이름
        
    Returns:
        str: 저장된 파일 경로
    """
    # 로그 저장 디렉토리 생성
    logs_dir = pathlib.Path(__file__).parent.parent / "logs" / "final_prompts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 현재 날짜와 시간으로 파일명 생성 (YYYYMMDD-HHMM 형식)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    shop_name_part = f"_{shop_name}" if shop_name else ""
    log_filename = f"{timestamp}{shop_name_part}_final_prompt.txt"
    log_file_path = logs_dir / log_filename
    
    # 파일에 저장
    try:
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("LLM에 최종 전달되는 프롬프트 전체\n")
            f.write(f"저장 시간: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분 %S초')}\n")
            f.write(f"상점명: {shop_name or 'N/A'}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("[시스템 프롬프트]\n")
            f.write("-" * 40 + "\n")
            f.write(system_prompt)
            f.write("\n\n")
            
            f.write("[사용자 프롬프트]\n")
            f.write("-" * 40 + "\n")
            f.write(user_prompt)
            f.write("\n\n")
            
            f.write("=" * 80 + "\n")
            f.write("파일 끝\n")
            
        print(f"최종 프롬프트가 {log_file_path} 파일에 저장되었습니다.")
        
    except Exception as e:
        print(f"최종 프롬프트 저장 중 오류 발생: {str(e)}")
        return "저장 실패"
    
    return str(log_file_path)


# 프롬프트 저장을 위한 추가 코드
# 이 코드를 services/llm_service.py의 255-257 라인 사이에 추가하세요:
"""
        # 프롬프트 저장
        try:
            from services.prompt_saver import save_final_prompt_to_file
            save_final_prompt_to_file(system_prompt, user_prompt, shop_name)
        except Exception as e:
            print(f"프롬프트 저장 중 오류: {str(e)}")
"""

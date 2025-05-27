import time
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

class ProgressPhase(Enum):
    """진행 단계 정의"""
    PREPROCESSING_COMPLETE = ("대화내용 전처리 완료", 10)
    PRODUCT_ANALYSIS_START = ("주문가능 품목 분석 요청 시작", 15)
    PRODUCT_ANALYSIS_COMPLETE = ("주문가능 품목 응답 받음", 25)
    MAIN_ANALYSIS_START = ("메인 분석(timebase)을 위한 LLM 호출 시작", 30)
    MAIN_ANALYSIS_60S = ("메인 분석을 위한 LLM 호출 시작 후 60초 경과", 40)
    MAIN_ANALYSIS_240S = ("메인 분석을 위한 LLM 호출 시작 후 240초 경과", 50)
    MAIN_ANALYSIS_480S = ("메인 분석을 위한 LLM 호출 시작 후 480초 경과", 70)
    MAIN_ANALYSIS_600S = ("메인 분석을 위한 LLM 호출 시작 후 600초 경과", 85)
    MAIN_ANALYSIS_COMPLETE = ("메인 분석 응답 수신", 95)
    FINAL_PROCESSING_COMPLETE = ("메인 분석 바탕으로 주문자별 정보 등 기타 정보 생성 완료", 100)
    
    def __init__(self, description: str, progress: int):
        self.description = description
        self.progress = progress

class EnhancedProgressLogger:
    """향상된 진행 상태 추적기"""
    
    def __init__(self, job_id: str, callback: Optional[Callable] = None):
        self.job_id = job_id
        self.callback = callback
        self.logs = []
        self.current_phase = None
        self.current_progress = 0
        self.main_analysis_start_time = None
        self.timer_thread = None
        self.timer_stop_event = threading.Event()
        
    def add_log(self, phase: ProgressPhase, details: List[str]):
        """진행 상태 로그 추가"""
        self.current_phase = phase
        self.current_progress = phase.progress
        
        log_entry = {
            "phase": phase.description,
            "progress": phase.progress,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.logs.append(log_entry)
        
        print(f"[{self.job_id}] {phase.description} ({phase.progress}%): {', '.join(details)}")
        
        # 콜백 함수 호출
        if self.callback:
            self.callback(self.get_status())
    
    def start_main_analysis_timer(self):
        """메인 분석 타이머 시작"""
        self.main_analysis_start_time = time.time()
        self.timer_stop_event.clear()
        
        def update_progress():
            """시간 기반 진행률 업데이트"""
            time_thresholds = [
                (60, ProgressPhase.MAIN_ANALYSIS_60S),
                (240, ProgressPhase.MAIN_ANALYSIS_240S),
                (480, ProgressPhase.MAIN_ANALYSIS_480S),
                (600, ProgressPhase.MAIN_ANALYSIS_600S)
            ]
            
            for seconds, phase in time_thresholds:
                if self.timer_stop_event.is_set():
                    break
                    
                # 대기 시간 계산
                elapsed = time.time() - self.main_analysis_start_time
                wait_time = seconds - elapsed
                
                if wait_time > 0:
                    # 대기 (1초 단위로 체크하여 즉시 중단 가능)
                    for _ in range(int(wait_time)):
                        if self.timer_stop_event.wait(1):
                            return
                
                # 메인 분석이 아직 완료되지 않았으면 진행률 업데이트
                if self.current_phase and self.current_phase.progress < ProgressPhase.MAIN_ANALYSIS_COMPLETE.progress:
                    elapsed = int(time.time() - self.main_analysis_start_time)
                    self.add_log(phase, [f"경과 시간: {elapsed}초"])
        
        # 백그라운드 스레드 생성
        self.timer_thread = threading.Thread(target=update_progress, daemon=True)
        self.timer_thread.start()
    
    def stop_main_analysis_timer(self):
        """메인 분석 타이머 중지"""
        if self.timer_thread and self.timer_thread.is_alive():
            self.timer_stop_event.set()
            self.timer_thread.join(timeout=1)
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            "job_id": self.job_id,
            "current_phase": self.current_phase.description if self.current_phase else None,
            "current_progress": self.current_progress,
            "logs": self.logs
        }
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """로그 목록 반환"""
        return self.logs.copy()

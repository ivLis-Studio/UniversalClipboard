import threading
import time
import pyperclip
from PyQt6.QtCore import QThread, pyqtSignal

from config_manager import load_config, save_config, MAX_HISTORY_ITEMS

class ClipboardMonitorThread(QThread):
    """
    클립보드 내용 변경을 감지하고 저장하는 스레드 클래스
    """
    new_clipboard_item = pyqtSignal(str)
    clipboard_history = []
    _running = True
    _lock = threading.Lock()

    def __init__(self, initial_history):
        """
        초기화 함수
        
        Args:
            initial_history: 초기 클립보드 히스토리 리스트
        """
        super().__init__()
        ClipboardMonitorThread.clipboard_history = list(initial_history)
        self._last_copied_text = None
        try:
            self._last_copied_text = pyperclip.paste()
        except pyperclip.PyperclipException:
            self._last_copied_text = ""

    def run(self):
        """
        스레드 실행 함수
        클립보드 내용 변경을 모니터링하고 변경 시 저장
        """
        while self._running:
            try:
                current_text = pyperclip.paste()
                if isinstance(current_text, str) and current_text != self._last_copied_text and current_text.strip():
                    # 현재 클립보드 내용이 변경되었고 유효한 경우
                    self._last_copied_text = current_text  # 먼저 마지막 복사된 텍스트 업데이트
                    
                    # 중복 확인 및 히스토리에 추가
                    with self._lock:
                        # 이미 있는 항목이면 제거하고 맨 뒤로 이동
                        if current_text in ClipboardMonitorThread.clipboard_history:
                            ClipboardMonitorThread.clipboard_history.remove(current_text)
                        
                        # 최대 항목 수 제한
                        if len(ClipboardMonitorThread.clipboard_history) >= MAX_HISTORY_ITEMS:
                            ClipboardMonitorThread.clipboard_history.pop(0)
                        
                        # 새 항목 추가
                        ClipboardMonitorThread.clipboard_history.append(current_text)
                        
                        # 설정 파일에 저장
                        config_data = load_config()
                        config_data["history"] = list(ClipboardMonitorThread.clipboard_history)
                        save_config(config_data)
                    
                    # 변경 이벤트 발생 - 항상 발생하여 UI가 업데이트되도록 함
                    print(f"클립보드 변경 감지: {current_text[:30]}...")
                    self.new_clipboard_item.emit(current_text)
            except pyperclip.PyperclipException:
                pass
            except Exception as e:
                # 로깅 추가
                print(f"클립보드 모니터링 오류: {e}")
            time.sleep(0.5)
        print("ClipboardMonitorThread: 중지됨.")

    def stop(self):
        """
        스레드 정지 함수
        """
        print("ClipboardMonitorThread: stop() 호출됨.")
        self._running = False

    @staticmethod
    def get_history():
        """
        현재 클립보드 히스토리 반환 함수
        
        Returns:
            현재 클립보드 히스토리 리스트
        """
        with ClipboardMonitorThread._lock:
            history = list(ClipboardMonitorThread.clipboard_history)
            print(f"클립보드 히스토리 가져오기: {len(history)}개 항목")
            
            # 설정 파일에서 히스토리 재로드(히스토리가 비어있을 경우)
            if not history:
                try:
                    config_data = load_config()
                    if "history" in config_data and config_data["history"]:
                        print("설정 파일에서 히스토리 복원 시도")
                        history = list(config_data["history"])
                        # 히스토리 복원
                        ClipboardMonitorThread.clipboard_history = history
                        print(f"설정 파일에서 {len(history)}개 항목 복원됨")
                except Exception as e:
                    print(f"히스토리 복원 중 오류: {e}")
            
            return history

    @staticmethod
    def add_item_manually(item_text, set_clipboard=True):
        """
        수동으로 항목 추가하는 함수
        
        Args:
            item_text: 추가할 텍스트
            set_clipboard: 클립보드에 실제로 복사할지 여부 (기본값: True)
        """
        if item_text:
            if set_clipboard:
                pyperclip.copy(item_text)
            with ClipboardMonitorThread._lock:
                if item_text in ClipboardMonitorThread.clipboard_history:
                    ClipboardMonitorThread.clipboard_history.remove(item_text)
                ClipboardMonitorThread.clipboard_history.append(item_text)
                if len(ClipboardMonitorThread.clipboard_history) > MAX_HISTORY_ITEMS:
                    ClipboardMonitorThread.clipboard_history.pop(0) 
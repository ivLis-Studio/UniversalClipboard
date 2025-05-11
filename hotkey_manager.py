import sys
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from pynput import keyboard
from pynput.keyboard import Key, KeyCode, Controller
from config_manager import format_hotkey_for_display
import time

class HotkeyListenerThread(QThread):
    """
    등록된 단축키 조합을 감지하는 스레드 클래스
    """
    hotkey_pressed_signal = pyqtSignal()

    def __init__(self, hotkey_config):
        """
        초기화 함수
        
        Args:
            hotkey_config: 단축키 설정 딕셔너리
        """
        super().__init__()
        self.hotkey_config = hotkey_config
        self.pressed_keys = set()
        self.listener_instance = None
        self._should_run = True
        # 마지막 단축키 처리 시간 추적
        self.last_hotkey_time = 0
        # 키보드 컨트롤러 (백스페이스 시뮬레이션용)
        self.keyboard = Controller()
        # 백스페이스 필요 플래그
        self.need_backspace = False

    def run(self):
        """
        스레드 실행 함수
        키보드 이벤트를 감지하고 설정된 단축키와 일치하는지 확인
        """
        target_modifiers = set()
        for mod_name in self.hotkey_config.get("modifiers", []):
            try: 
                key_attr = getattr(keyboard.Key, mod_name)
                target_modifiers.add(key_attr)
            except AttributeError: 
                print(f"HotkeyListenerThread: 알 수 없는 수정자 키 '{mod_name}'")
                
        target_key_str = self.hotkey_config.get("key", "")
        target_key_obj = None
        
        if not target_key_str: 
            print("HotkeyListenerThread: 대상 키 문자열이 설정에 없습니다. 리스너가 효과적으로 시작되지 않습니다.")
            return
        
        # 설정에 '\x16'과 같은 제어 문자가 있는 경우 처리
        if len(target_key_str) == 1 and ('\x00' < target_key_str < '\x20'):
            print(f"HotkeyListenerThread: 경고 - 대상 키 '{repr(target_key_str)}'는 제어 문자입니다. 단축키가 예상대로 작동하지 않을 수 있습니다.")
            # KeyCode 생성 시도
            try:
                target_key_obj = keyboard.KeyCode.from_char(target_key_str)
            except Exception as e:
                print(f"HotkeyListenerThread: 제어 문자 '{repr(target_key_str)}'에서 KeyCode를 생성할 수 없습니다: {e}")
                return
        elif len(target_key_str) == 1: 
            target_key_obj = keyboard.KeyCode.from_char(target_key_str)
        else:  # 'space', 'enter'와 같은 특수 키
            try: 
                target_key_obj = getattr(keyboard.Key, target_key_str)
            except AttributeError: 
                print(f"HotkeyListenerThread: 알 수 없는 특수 키 이름 '{target_key_str}'")
                return
        
        if not target_key_obj: 
            print("HotkeyListenerThread: 대상 키 객체를 확인할 수 없습니다. 리스너를 중지합니다.")
            return

        # 디버깅 정보 추가
        print(f"HotkeyListenerThread: 리스너 시작됨. 단축키: {format_hotkey_for_display(self.hotkey_config)}")
        print(f"HotkeyListenerThread: 타겟 키 정보: {target_key_obj}, 타입: {type(target_key_obj)}")
        if hasattr(target_key_obj, 'vk'):
            print(f"HotkeyListenerThread: 타겟 키 VK: {target_key_obj.vk}")
        if hasattr(target_key_obj, 'char'):
            print(f"HotkeyListenerThread: 타겟 키 문자: {repr(target_key_obj.char)}")
        print(f"HotkeyListenerThread: 타겟 수정자 키: {target_modifiers}")

        def on_press(key):
            try:
                # 키 정보 로깅 (디버깅용)
                # print(f"키 누름: {key}")
                
                # 수정자 키를 간소화하여 처리 (좌우 구분 없음)
                simple_key = key
                if key in (keyboard.Key.ctrl_r, keyboard.Key.ctrl_l): 
                    simple_key = keyboard.Key.ctrl_l
                elif key in (keyboard.Key.shift_r, keyboard.Key.shift_l): 
                    simple_key = keyboard.Key.shift_l
                elif key in (keyboard.Key.alt_r, keyboard.Key.alt_l): 
                    simple_key = keyboard.Key.alt_l
                elif sys.platform == "darwin" and key in (keyboard.Key.cmd_r, keyboard.Key.cmd_l): 
                    simple_key = keyboard.Key.cmd
                
                self.pressed_keys.add(simple_key)

                # 단축키 일치 확인 
                is_target_key_pressed_now = False
                
                # 타겟 키와 현재 키 비교
                if isinstance(target_key_obj, keyboard.KeyCode) and isinstance(key, keyboard.KeyCode):
                    # 가상 키 코드로 비교
                    if hasattr(key, 'vk') and hasattr(target_key_obj, 'vk') and key.vk == target_key_obj.vk:
                        is_target_key_pressed_now = True
                    # 문자값으로 비교 (대소문자 구분 없이)
                    elif (hasattr(key, 'char') and key.char and 
                          hasattr(target_key_obj, 'char') and target_key_obj.char and 
                          key.char.lower() == target_key_obj.char.lower()):
                        is_target_key_pressed_now = True
                elif simple_key == target_key_obj:  # 특수 키인 경우
                    is_target_key_pressed_now = True

                if is_target_key_pressed_now:
                    # 필요한 모든 수정자 키가 눌렸는지 확인
                    current_pressed_modifiers = {k for k in self.pressed_keys if k in target_modifiers}
                    all_target_mods_pressed = (len(current_pressed_modifiers) == len(target_modifiers))
                    
                    if all_target_mods_pressed:
                        # 다른 수정자 키가 눌리지 않았는지 확인
                        all_relevant_modifiers = {keyboard.Key.ctrl_l, keyboard.Key.shift_l, keyboard.Key.alt_l}
                        if sys.platform == "darwin": 
                            all_relevant_modifiers.add(keyboard.Key.cmd)
                        
                        extra_modifiers_pressed = False
                        for pressed_mod_key in self.pressed_keys:
                            if (pressed_mod_key in all_relevant_modifiers and 
                                pressed_mod_key not in target_modifiers and 
                                pressed_mod_key != target_key_obj):
                                extra_modifiers_pressed = True
                                break

                        if not extra_modifiers_pressed:
                            # 중복 처리 방지 (시간 간격 체크)
                            current_time = time.time()
                            if current_time - self.last_hotkey_time > 0.3:
                                self.last_hotkey_time = current_time
                                print("핫키 조합이 일치함 - 신호 발생!")
                                
                                # 입력된 문자 삭제를 위해 백스페이스 필요 플래그 설정
                                if isinstance(key, keyboard.KeyCode) and hasattr(key, 'char') and key.char:
                                    self.need_backspace = True
                                    
                                # 핫키 감지 이벤트 발생
                                self.hotkey_pressed_signal.emit()
                                
                                # 0.01초 후 백스페이스 시뮬레이션
                                if self.need_backspace:
                                    time.sleep(0.01)
                                    try:
                                        self.keyboard.press(Key.backspace)
                                        self.keyboard.release(Key.backspace)
                                        print("백스페이스 키 시뮬레이션 완료")
                                    except Exception as e:
                                        print(f"백스페이스 키 시뮬레이션 오류: {e}")
                                    self.need_backspace = False
                                
                                # 키 상태 초기화
                                self.pressed_keys.clear()
            except Exception as e: 
                print(f"HotkeyListenerThread: 키 처리 중 오류: {e}")
            
            return True  # 모든 키 이벤트를 시스템으로 전달

        def on_release(key):
            try:
                # 키 해제 정보 로깅 (디버깅용)
                # print(f"키 해제: {key}")
                
                simple_key = key
                if key in (keyboard.Key.ctrl_r, keyboard.Key.ctrl_l): 
                    simple_key = keyboard.Key.ctrl_l
                elif key in (keyboard.Key.shift_r, keyboard.Key.shift_l): 
                    simple_key = keyboard.Key.shift_l
                elif key in (keyboard.Key.alt_r, keyboard.Key.alt_l): 
                    simple_key = keyboard.Key.alt_l
                elif sys.platform == "darwin" and key in (keyboard.Key.cmd_r, keyboard.Key.cmd_l): 
                    simple_key = keyboard.Key.cmd
                    
                if simple_key in self.pressed_keys: 
                    self.pressed_keys.remove(simple_key)
            except Exception as e: 
                print(f"HotkeyListenerThread: 키 해제 중 오류: {e}")
                
        try:
            # 모든 키보드 이벤트를 시스템으로 전달하도록 설정
            self.listener_instance = keyboard.Listener(
                on_press=on_press, 
                on_release=on_release, 
                suppress=False
            )
            self.listener_instance.start()
            
            # 스레드 종료 플래그
            self._should_run = True
            
            # 이벤트 기반 방식으로 관리
            while (self.listener_instance and 
                  self.listener_instance.is_alive() and 
                  self.isRunning() and 
                  self._should_run):
                time.sleep(0.1)  # CPU 사용량 감소를 위한 짧은 대기
        except Exception as e:
            print(f"HotkeyListenerThread: 리스너 오류: {e}")
        finally:
            if self.listener_instance and self.listener_instance.is_alive(): 
                self.listener_instance.stop()
            print("HotkeyListenerThread: 리스너가 중지되었습니다. run 메서드가 종료됩니다.")

    def stop(self):
        """
        스레드 정지 함수
        """
        print("HotkeyListenerThread: stop() 호출됨.")
        self._should_run = False  # 스레드 종료 플래그 설정
        if self.listener_instance:
            self.listener_instance.stop()


class HotkeyRecordingThread(QThread):
    """
    새 단축키 입력을 기록하는 스레드 클래스
    """
    key_combination_recorded = pyqtSignal(list, str)
    recording_canceled = pyqtSignal()
    update_display_signal = pyqtSignal(str)

    def __init__(self, parent_dialog_ref): 
        """
        초기화 함수
        
        Args:
            parent_dialog_ref: 부모 다이얼로그 참조 (QObject PARENT 용도)
        """
        super().__init__(parent_dialog_ref) # QThread의 부모로 parent_dialog_ref 전달
        self._listener = None

    def run(self):
        """
        스레드 실행 함수
        키보드 이벤트를 감지하고 단축키 조합 기록
        """
        self.recorded_modifiers = []
        self.recorded_key = None
        
        def on_press(key):
            try:
                if key == keyboard.Key.esc:
                    if self._listener: 
                        self._listener.stop()
                    self.recording_canceled.emit()
                    return False
                    
                mod_name, key_val = None, None
                
                if isinstance(key, keyboard.Key):  # 수정자 또는 특수 키(space, enter, F1 등)
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r): 
                        mod_name = "ctrl_l"
                    elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r): 
                        mod_name = "shift_l"
                    elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r): 
                        mod_name = "alt_l"
                    elif sys.platform == "darwin" and key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r): 
                        mod_name = "cmd_l"
                    else:  # 다른 특수 키(Key.space, Key.enter, Key.f1 등)는 주 키가 됨
                        key_val = key.name 
                elif isinstance(key, keyboard.KeyCode) and key.char:  # 문자 키
                    # \x01~\x1A 같은 제어 문자 필터링
                    # 수정자 키가 눌리지 않은 경우 pynput은 보통 정확한 문자를 제공함
                    if ('\x00' < key.char < '\x20') and key.char not in ['\t', '\n', '\r']:
                        print(f"HotkeyRecordingThread: 주 키 부분에서 제어 문자 {repr(key.char)}을(를) 무시합니다.")
                        # key_val을 설정하지 않음; 비수정자, 비제어 문자 키를 기다림
                    else:
                        key_val = key.char.lower()  # 'a'는 기록하되 'A'는 하지 않음

                cfg = {
                    "modifiers": list(self.recorded_modifiers), 
                    "key": self.recorded_key
                }
                
                if mod_name and mod_name not in self.recorded_modifiers: 
                    self.recorded_modifiers.append(mod_name)
                    cfg["modifiers"] = list(self.recorded_modifiers)
                elif key_val and not self.recorded_key:  # 첫 비수정자 키가 주 키
                    self.recorded_key = key_val
                    cfg["key"] = self.recorded_key
                
                self.update_display_signal.emit(format_hotkey_for_display(cfg))
                
                if self.recorded_key:  # 주 키가 설정된 경우
                    # 주 키가 눌리면 조합이 완료됨
                    # (예: Ctrl + Shift + V - V가 눌리면 조합 완료)
                    if self._listener: 
                        self._listener.stop()
                    self.key_combination_recorded.emit(list(self.recorded_modifiers), self.recorded_key)
                    return False  # 리스너 중지
                return True
            except Exception:
                if self._listener: 
                    self._listener.stop()
                self.recording_canceled.emit()
                return False
                
        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.start()
            self._listener.join()
        except Exception: 
            self.recording_canceled.emit()
        finally:
            if self._listener and self._listener.is_alive(): 
                self._listener.stop()
            self._listener = None

    def stop_listener_and_quit(self):
        """
        리스너 중지 및 스레드 종료 함수
        """
        if self._listener: 
            self._listener.stop()
        self.quit() 
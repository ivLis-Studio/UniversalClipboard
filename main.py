import sys
import os
import threading
import time
import traceback 

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

from PIL import Image as PILImage
from pystray import Icon as PyStrayIcon, MenuItem as PyStrayMenuItem

# --- 모듈화된 파일들에서 기능 import ---
from config_manager import (
    load_config, save_config, 
    DEFAULT_HOTKEY_CONFIG, CONFIG_FILE, format_hotkey_for_display
)
from clipboard_monitor import ClipboardMonitorThread
from hotkey_manager import HotkeyListenerThread
from ui_components import ClipboardHistoryPopup, SettingsDialog


# --- Main Application (QObject) ---
class ClipboardManagerApp(QObject):
    _request_toggle_popup_signal = pyqtSignal()
    _request_open_settings_signal = pyqtSignal()
    _request_quit_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.app = QApplication.instance() 
        if not self.app: self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.config = load_config()
        
        self.clipboard_history_popup = ClipboardHistoryPopup()
        self.clipboard_history_popup.paste_requested_signal.connect(self.on_paste_requested)
        
        self.clipboard_monitor_thread = ClipboardMonitorThread(self.config.get("history", []))
        self.clipboard_monitor_thread.new_clipboard_item.connect(self.handle_new_clipboard_item)
        self.clipboard_monitor_thread.start()
        
        # 초기화 시 클립보드 히스토리 로드
        self.clipboard_history_popup.current_history_items = self.clipboard_monitor_thread.get_history()
        
        # 단축키 표시 업데이트
        current_hotkey_conf = self.config.get("hotkey", DEFAULT_HOTKEY_CONFIG).copy()
        self.clipboard_history_popup.status_label.setText(
            "단축키: " + format_hotkey_for_display(current_hotkey_conf)
        )
        
        self.hotkey_listener_thread = None
        self.setup_hotkey_listener()
        
        self.settings_dialog = None # SettingsDialog 인스턴스는 필요할 때 생성
        
        self._request_toggle_popup_signal.connect(self.toggle_clipboard_history_popup)
        self._request_open_settings_signal.connect(self.open_settings_dialog)
        self._request_quit_signal.connect(self.quit_application)
        self.create_tray_icon()

    def setup_hotkey_listener(self):
        """단축키 감지 스레드 설정/재설정"""
        print("단축키 리스너 설정...")
        
        # 기존 리스너가 실행 중이면 중지
        if self.hotkey_listener_thread and self.hotkey_listener_thread.isRunning():
            print("기존 핫키 리스너 중지...")
            self.hotkey_listener_thread.stop()
            self.hotkey_listener_thread.wait(1000)
            print("기존 핫키 리스너 중지 완료")
            
        # 새 리스너 생성 및 시작
        current_hotkey_conf = self.config.get("hotkey", DEFAULT_HOTKEY_CONFIG).copy()
        self.hotkey_listener_thread = HotkeyListenerThread(current_hotkey_conf)
        self.hotkey_listener_thread.hotkey_pressed_signal.connect(self.toggle_clipboard_history_popup)
        self.hotkey_listener_thread.start()
        print(f"새 핫키 리스너 시작됨: {format_hotkey_for_display(current_hotkey_conf)}")

    def create_tray_icon(self):
        icon_image, icon_path = None, None
        try:
            if getattr(sys, 'frozen', False):
                app_path = os.path.dirname(sys.executable)
            else:
                app_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(app_path, "icon.png")
            
            if os.path.exists(icon_path):
                icon_image = PILImage.open(icon_path)
                icon_image = icon_image.convert('RGBA') if icon_image.mode != 'RGBA' else icon_image
        except Exception as e:
            print(f"Error loading icon image: {e}")
            icon_image = None

        if icon_image is None:
            icon_image = PILImage.new('RGBA', (64,64), (70,130,180,255)) # 기본 아이콘

        try:
            menu_items = (
                PyStrayMenuItem('클립보드 보기', self.toggle_clipboard_history_popup_threadsafe),
                PyStrayMenuItem('설정', self.open_settings_dialog_threadsafe),
                PyStrayMenuItem('종료', self.quit_application_threadsafe)
            )
            self.tray_icon = PyStrayIcon("clipboard_manager", icon_image, "클립보드 매니저", menu_items)
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
        except Exception as e:
            print(f"pystray failed: {e}. Using Qt fallback.")
            q_icon = QIcon(icon_path) if icon_path and os.path.exists(icon_path) else QIcon.fromTheme("edit-copy")
            if q_icon.isNull():
                pixmap = QPixmap(64,64)
                pixmap.fill(QColor("steelblue"))
                q_icon = QIcon(pixmap)

            self.qt_tray_icon = QSystemTrayIcon(q_icon, self)
            self.qt_tray_icon.setToolTip("클립보드 매니저 (Qt)")
            menu = QMenu()
            menu.addAction("클립보드 보기", self.toggle_clipboard_history_popup)
            menu.addAction("설정", self.open_settings_dialog)
            menu.addSeparator()
            menu.addAction("종료", self.quit_application)
            self.qt_tray_icon.setContextMenu(menu)
            self.qt_tray_icon.show()

    def handle_new_clipboard_item(self, item_text):
        """새 클립보드 항목이 감지되었을 때 처리"""
        # 현재 클립보드 히스토리 가져오기
        current_history = ClipboardMonitorThread.get_history()
        
        # 팝업이 열려 있을 때만 히스토리 실시간 업데이트
        if self.clipboard_history_popup.isVisible():
            print(f"새 클립보드 항목 감지됨: {item_text[:30]}... - 목록 업데이트")
            self.clipboard_history_popup.update_history(current_history)

    @pyqtSlot(str)
    def on_paste_requested(self, text_to_paste):
        """
        클립보드 붙여넣기 요청 처리
        
        Args:
            text_to_paste: 붙여넣을 텍스트
        """
        print(f"붙여넣기 요청: {text_to_paste[:30]}...")
        
        # 팝업이 화면에서 사라지게 하기 (UI_components에서 이미 처리되고 있지만 확실히 하기 위해)
        if self.clipboard_history_popup.isVisible():
            self.clipboard_history_popup.hide_popup()
            
        # 팝업의 _perform_paste 메서드 호출 (자체적으로 클립보드 설정 및 키 시뮬레이션 수행)
        self.clipboard_history_popup._perform_paste(text_to_paste)

    @pyqtSlot()
    def toggle_clipboard_history_popup(self):
        # 현재 상태 확인
        is_visible = self.clipboard_history_popup.isVisible()
        current_opacity = self.clipboard_history_popup.opacity_effect.opacity()
        animation_state = self.clipboard_history_popup.animation.state()
        
        # 디버깅 정보 출력
        print(f"토글 호출됨: 보이기={is_visible}, 투명도={current_opacity}, 애니메이션 상태={animation_state}")
        
        # 단축키 리스너 생존 확인, 종료된 경우 재시작
        if self.hotkey_listener_thread and not self.hotkey_listener_thread.isRunning():
            print("단축키 리스너가 종료됨, 재시작합니다...")
            self.setup_hotkey_listener()
        
        # 완전히 표시된 상태
        if is_visible and abs(current_opacity - 1.0) < 0.01:
            print("팝업 숨기기...")
            self.clipboard_history_popup.hide_popup()
        # 숨겨진 상태 또는 사라지는 중
        elif not is_visible or abs(current_opacity - 0.0) < 0.01:
            print("팝업 표시하기...")
            # 표시하기 전에 최신 클립보드 히스토리로 업데이트
            self.refresh_clipboard_history()
            self.clipboard_history_popup.show_popup_animated()
        # 애니메이션 진행 중 - 현재 상태의 반대로 전환
        else:
            print(f"애니메이션 진행 중 (opacity={current_opacity}), 현재 상태 전환")
            if current_opacity > 0.5:
                self.clipboard_history_popup.hide_popup()
            else:
                # 표시하기 전에 최신 클립보드 히스토리로 업데이트
                self.refresh_clipboard_history()
            self.clipboard_history_popup.show_popup_animated()
    
    def refresh_clipboard_history(self):
        """최신 클립보드 히스토리로 UI 업데이트"""
        try:
            current_history = ClipboardMonitorThread.get_history()
            print(f"클립보드 히스토리 새로고침: {len(current_history)}개 항목")
            self.clipboard_history_popup.current_history_items = current_history
            self.clipboard_history_popup.update_displayed_items()
        except Exception as e:
            print(f"클립보드 히스토리 새로고침 중 오류: {e}")

    def toggle_clipboard_history_popup_threadsafe(self):
        self._request_toggle_popup_signal.emit()

    @pyqtSlot()
    def open_settings_dialog(self):
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.activateWindow()
            return
        
        current_conf = self.config.get("hotkey", DEFAULT_HOTKEY_CONFIG).copy()
        parent_widget = QApplication.activeWindow() 
        self.settings_dialog = SettingsDialog(current_conf, parent=parent_widget) 
        self.settings_dialog.hotkey_updated.connect(self.on_hotkey_settings_updated)
        self.settings_dialog.show()
        self.settings_dialog.activateWindow()
        self.settings_dialog.raise_()

    def open_settings_dialog_threadsafe(self):
        self._request_open_settings_signal.emit()

    @pyqtSlot(dict)
    def on_hotkey_settings_updated(self, new_hotkey_config):
        """단축키 설정 업데이트 처리"""
        print(f"단축키 설정 업데이트 요청: {new_hotkey_config}")
        
        # 단축키 설정 업데이트 및 저장
        self.config["hotkey"] = new_hotkey_config
        save_config(self.config)
        
        # 단축키 표시 업데이트
        self.clipboard_history_popup.status_label.setText(
            "단축키: " + format_hotkey_for_display(new_hotkey_config)
        )
        
        # 핫키 리스너 재설정
        self.setup_hotkey_listener()
        print(f"단축키가 업데이트됨: {format_hotkey_for_display(new_hotkey_config)}")

    def run(self):
        print("Starting application event loop...")
        
        # 리스너 체크 타이머 설정
        self.check_listener_timer = QTimer()
        self.check_listener_timer.timeout.connect(self.check_and_restart_listener)
        self.check_listener_timer.start(10000)  # 10초마다 리스너 상태 확인
        
        if not self.app:
            return -1
        return self.app.exec()
        
    def check_and_restart_listener(self):
        """단축키 리스너 상태를 확인하고 필요시 재시작"""
        if self.hotkey_listener_thread and not self.hotkey_listener_thread.isRunning():
            print("단축키 리스너 스레드가 종료됨, 자동으로 재시작합니다...")
            self.setup_hotkey_listener()

    @pyqtSlot()
    def quit_application(self):
        print("SLOT: quit_application called")
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.stop()
            if hasattr(self, 'tray_thread') and self.tray_thread.is_alive():
                self.tray_thread.join(timeout=0.5)

            if self.hotkey_listener_thread and self.hotkey_listener_thread.isRunning():
                self.hotkey_listener_thread.stop()
                self.hotkey_listener_thread.wait(500)

            if self.clipboard_monitor_thread and self.clipboard_monitor_thread.isRunning():
                self.clipboard_monitor_thread.stop()
                self.clipboard_monitor_thread.wait(500)
            
            if self.settings_dialog and hasattr(self.settings_dialog, '_recording_listener_thread'):
                rec_thread = self.settings_dialog._recording_listener_thread
                if rec_thread and rec_thread.isRunning():
                    rec_thread.stop_listener_and_quit() # HotkeyRecordingThread에 해당 메서드 필요
                    rec_thread.wait(200)

            if self.app:
                self.app.quit()
        except Exception as e:
            print(f"Error during quit_application: {e}")
            traceback.print_exc()

    def quit_application_threadsafe(self):
        self._request_quit_signal.emit()

if __name__ == "__main__":
    print("Application starting...")
    if sys.platform == "win32":
        try:
            from ctypes import windll
            if hasattr(windll.shcore, 'SetProcessDpiAwareness'):
                try: result = windll.shcore.SetProcessDpiAwareness(2) 
                except Exception: 
                    try: result = windll.shcore.SetProcessDpiAwareness(1) 
                    except Exception: pass 
            elif hasattr(windll.user32, 'SetProcessDPIAware'):
                try: windll.user32.SetProcessDPIAware()
                except Exception: pass 
        except Exception: pass 

    manager_app = ClipboardManagerApp()
    exit_code = manager_app.run()
    print(f"Application finished with exit code: {exit_code}")
    sys.exit(exit_code)
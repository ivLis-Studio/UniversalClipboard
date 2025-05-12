import sys
import time
import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QApplication, QDialog,
    QSizePolicy, QGraphicsOpacityEffect, QToolButton, QGridLayout,
    QListWidget, QListWidgetItem, QCheckBox, QComboBox
)
from PyQt6.QtGui import (
    QCursor, QPixmap, QPainter, QColor, QFont, QPalette, 
    QIcon, QFontMetrics, QLinearGradient, QBrush, QTextOption
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QRect, QPropertyAnimation, 
    QEasingCurve, QEvent, pyqtSlot, QSize, QPoint, QMargins
)

from pynput.keyboard import Key, Controller as KeyboardController
import pyperclip
import re
import webbrowser

from config_manager import CLIP_PREVIEW_MAX_LEN, format_hotkey_for_display
from clipboard_monitor import ClipboardMonitorThread
from hotkey_manager import HotkeyRecordingThread

# 공통 색상 및 스타일 상수
COLOR_PRIMARY = "#0078D7"       # 주요 색상 (파란색, Microsoft 스타일)
COLOR_SECONDARY = "#E1EFFA"     # 보조 색상 (밝은 파란색)
COLOR_ACCENT = "#00BAFF"        # 강조 색상 (밝은 청록색)
COLOR_BG_LIGHT = "#F9F9F9"      # 배경색 (밝은 테마)
COLOR_TEXT_LIGHT = "#212121"    # 텍스트 색상 (밝은 테마)
COLOR_BG_DARK = "#202020"       # 배경색 (다크 테마)
COLOR_TEXT_DARK = "#EFEFEF"     # 텍스트 색상 (다크 테마)
FONT_MAIN = "'Segoe UI', 'SF Pro Display', 'Malgun Gothic', sans-serif"  # 주요 폰트

class ClipboardHistoryPopup(QWidget):
    """
    클립보드 히스토리를 표시하는 팝업 윈도우 클래스
    완전히 새롭게 디자인된 모던한 UI
    """
    item_selected_signal = pyqtSignal(str) 
    paste_requested_signal = pyqtSignal(str) 

    def __init__(self):
        """
        초기화 함수
        """
        super().__init__()
        # 창 설정
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) 
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) 
        
        # 내부 상태 변수
        self.dark_mode = False  # 기본: 라이트 모드
        self.current_category = 0  # 0: 클립보드 히스토리
        self.keyboard_controller = KeyboardController()
        self.clipboard_times = {}  # 시간 표시용
        self.current_history_items = []
        self.filtered_items = []
        self.search_text = ""
        
        # 애니메이션 설정
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(100)
        self.animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        
        # 다크 모드 감지
        self.detect_system_theme()
        
        # UI 구성 요소 초기화
        self.init_ui()
        
        # 이벤트 필터 설치
        if QApplication.instance():
            QApplication.instance().installEventFilter(self)
    
    def detect_system_theme(self):
        """시스템 테마를 감지하여 다크 모드 설정"""
        palette = QApplication.palette()
        window_color = palette.color(QPalette.ColorRole.Window)
        self.dark_mode = window_color.lightness() < 128
    
    def init_ui(self):
        """UI 요소 초기화 및 배치"""
        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 중앙 컨테이너 (그림자 및 배경 효과용)
        self.container = QFrame(self)
        self.container.setObjectName("container")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(1, 1, 1, 1)
        container_layout.setSpacing(0)
        
        # 헤더 영역
        self.header = QFrame()
        self.header.setObjectName("header")
        self.header.setFixedHeight(50)  # 약간 낮은 헤더 높이
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)
        
        # 앱 로고 및 제목
        logo_layout = QHBoxLayout()
        app_icon = QLabel()
        icon_pixmap = QPixmap(20, 20)  # 아이콘 크기 약간 축소
        icon_pixmap.fill(Qt.GlobalColor.transparent)
        
        # 앱 아이콘 그리기
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        gradient = QLinearGradient(0, 0, 20, 20)
        gradient.setColorAt(0, QColor(COLOR_PRIMARY))
        gradient.setColorAt(1, QColor(COLOR_ACCENT))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(2, 2, 16, 16, 4, 4)
        painter.setPen(QColor("white"))
        painter.drawText(QRect(2, 2, 16, 16), Qt.AlignmentFlag.AlignCenter, "U")
        painter.end()
        
        app_icon.setPixmap(icon_pixmap)
        app_title = QLabel("UniPaste")
        app_title.setObjectName("appTitle")
        
        logo_layout.addWidget(app_icon)
        logo_layout.addWidget(app_title)
        logo_layout.addStretch()
        
        # 검색창
        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("검색...")
        self.search_box.textChanged.connect(self.filter_history)
        self.search_box.setMinimumWidth(200)
        
        # 우측 액션 버튼들
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        
        # 카테고리 선택 버튼들
        self.category_buttons = []
        categories = ["최근 기록", "자주 쓰는 항목", "메모장", "이메일 템플릿"]
        
        for i, category in enumerate(categories):
            btn = QPushButton(category)
            btn.setObjectName(f"categoryBtn{i}")
            btn.setProperty("category", True)
            btn.setProperty("selected", i == self.current_category)
            btn.setCheckable(True)
            btn.setChecked(i == self.current_category)
            btn.clicked.connect(lambda checked, idx=i: self.change_category(idx))
            self.category_buttons.append(btn)
            actions_layout.addWidget(btn)
        
        # 테마 전환 버튼
        self.theme_toggle_button = QToolButton()
        self.theme_toggle_button.setObjectName("themeToggle")
        self.theme_toggle_button.setText("🌙" if self.dark_mode else "☀️")
        self.theme_toggle_button.setToolTip("테마 전환")
        self.theme_toggle_button.clicked.connect(self.toggle_theme)
        
        # 헤더에 요소 배치
        header_layout.addLayout(logo_layout)
        header_layout.addStretch()
        header_layout.addWidget(self.search_box, 1)  # 1은 stretch factor
        header_layout.addLayout(actions_layout)
        header_layout.addWidget(self.theme_toggle_button)
        
        # 콘텐츠 영역
        self.content_area = QFrame()
        self.content_area.setObjectName("contentArea")
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(15, 10, 15, 10)  # 상하 여백 줄임
        
        # 클립보드 아이템 목록 영역
        self.items_list = QListWidget()
        self.items_list.setObjectName("itemsList")
        self.items_list.setFrameShape(QFrame.Shape.NoFrame)
        self.items_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.items_list.itemClicked.connect(self.on_item_clicked)
        self.items_list.setSpacing(10)  # 아이템 간 간격 증가
        self.items_list.setContentsMargins(0, 0, 0, 0)  # 리스트 위젯 여백 제거
        self.items_list.setStyleSheet("""
            QListWidget {
                padding: 0;
                background-color: transparent;
                border: none;
            }
            QListWidget::item { 
                padding: 0; 
                margin: 3px 0px;
                border-radius: 6px;
                border: none;
            }
        """)
        
        # 비어있을 때 표시할 메시지
        self.empty_message = QLabel("클립보드 항목이 없습니다")
        self.empty_message.setObjectName("emptyMessage")
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_message.setVisible(False)
        
        # 콘텐츠 영역에 위젯 추가
        content_layout.addWidget(self.items_list)
        content_layout.addWidget(self.empty_message)
        
        # 푸터 영역
        self.footer = QFrame()
        self.footer.setObjectName("footer")
        self.footer.setFixedHeight(30)  # 푸터 높이 줄임
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)
        
        # 단축키 표시
        self.status_label = QLabel("단축키: " + format_hotkey_for_display({"modifiers": ["shift"], "key": "+"}))
        self.status_label.setObjectName("statusLabel")
        
        # 설정 버튼
        self.settings_button = QPushButton("설정")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedWidth(60)
        self.settings_button.clicked.connect(self.open_settings)
        
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.settings_button)
        
        # 레이아웃에 구성 요소 추가
        container_layout.addWidget(self.header)
        container_layout.addWidget(self.content_area, 1)  # 1은 stretch factor로 늘어나게 함
        container_layout.addWidget(self.footer)
        main_layout.addWidget(self.container)
        
        # 스타일 적용
        self.apply_theme()
    
    def _open_url(self, url):
        """주어진 URL을 웹 브라우저에서 엽니다."""
        try:
            print(f"Opening URL: {url}")
            webbrowser.open(url)
            self.hide_popup() # 링크를 열면 팝업은 닫히도록
        except Exception as e:
            print(f"Error opening URL {url}: {e}")

    def apply_theme(self):
        """현재 테마(다크/라이트 모드)에 맞는 스타일 적용"""
        # 테마에 따른 색상 선택
        if self.dark_mode:
            bg_color = COLOR_BG_DARK
            text_color = COLOR_TEXT_DARK
            item_bg_color = "rgba(40, 40, 40, 255)" 
            item_hover_color = "rgba(60, 60, 60, 255)"
            header_bg_color = "rgba(30, 30, 30, 255)"
            border_color = "rgba(45, 45, 45, 255)"
        else:
            bg_color = COLOR_BG_LIGHT
            text_color = COLOR_TEXT_LIGHT
            item_bg_color = "rgba(240, 240, 240, 255)" 
            item_hover_color = "rgba(230, 230, 230, 255)"
            header_bg_color = "rgba(255, 255, 255, 255)"
            border_color = "rgba(220, 220, 220, 255)"
        
        # 전체 앱 스타일
        self.setStyleSheet(f"""
            QWidget {{
                font-family: {FONT_MAIN};
                color: {text_color};
                font-size: 10pt;
            }}
            
            #container {{
                background-color: {bg_color};
                border: none;
                border-radius: 0px;  /* 모서리 둥글기 제거 */
            }}
            
            #header {{
                background-color: {header_bg_color};
                border-bottom: 1px solid {border_color};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
            
            #footer {{
                background-color: {header_bg_color};
                border-top: 1px solid {border_color};
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            
            #appTitle {{
                font-size: 14pt;
                font-weight: bold;
                color: {COLOR_PRIMARY};
                margin-left: 5px;
            }}
            
            #searchBox {{
                background-color: {item_bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
                color: {text_color};
            }}
            
            QPushButton[category=true] {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 9.5pt;
                color: {text_color};
            }}
            
            QPushButton[category=true]:checked {{
                background-color: {COLOR_PRIMARY};
                color: white;
                font-weight: bold;
            }}
            
            QPushButton[category=true]:hover:!checked {{
                background-color: {item_hover_color};
            }}
            
            #themeToggle {{
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 2px;
                font-size: 14pt;
            }}
            
            #themeToggle:hover {{
                background-color: {item_hover_color};
            }}
            
            #contentArea {{
                background-color: {bg_color};
            }}
            
            #emptyMessage {{
                color: rgba(128, 128, 128, 180);
                font-size: 12pt;
                padding: 20px;
            }}
            
            #statusLabel {{
                color: rgba(128, 128, 128, 200);
                font-size: 9pt;
            }}
            
            #settingsButton {{
                background-color: transparent;
                border: 1px solid {border_color};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 9pt;
                color: {text_color};
            }}
            
            #settingsButton:hover {{
                background-color: {item_hover_color};
            }}
            
            /* 스크롤바 스타일 */
            QScrollBar:vertical {{
                border: none;
                background: {bg_color};
                width: 8px;
                margin: 0px;
            }}
            
            QScrollBar::handle:vertical {{
                background: rgba(128, 128, 128, 120);
                min-height: 20px;
                border-radius: 4px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: rgba(128, 128, 128, 180);
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        # 아이템 위젯은 ItemDelegate를 사용하므로 별도 스타일링 불필요

    def toggle_theme(self):
        """다크 모드와 라이트 모드 간 전환"""
        self.dark_mode = not self.dark_mode
        self.theme_toggle_button.setText("🌙" if self.dark_mode else "☀️")
        self.apply_theme()
        # 현재 표시된 클립보드 아이템 다시 그리기
        self.update_displayed_items()
    
    def eventFilter(self, obj, event):
        """외부 영역 클릭 시 팝업 숨김"""
        if obj == self and event.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            newly_focused_widget = QApplication.focusWidget()
            if not self.isAncestorOf(newly_focused_widget if newly_focused_widget else self): 
                self.hide_popup()
                return True
        return super().eventFilter(obj, event)
    
    def change_category(self, category_idx):
        """카테고리 변경"""
        if category_idx == self.current_category:
            return
            
        self.current_category = category_idx
        
        # 카테고리 버튼 상태 업데이트
        for i, btn in enumerate(self.category_buttons):
            is_selected = (i == category_idx)
            btn.setProperty("selected", is_selected)
            btn.setChecked(is_selected)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
        # 카테고리에 맞는 데이터 로드
        if category_idx == 0:  # 클립보드 히스토리
            self.current_history_items = ClipboardMonitorThread.get_history()
            self.filter_history(self.search_box.text())
        else:
            # 다른 카테고리는 현재 구현 전
            self.empty_message.setText(f"{self.category_buttons[category_idx].text()} 기능은 준비 중입니다.")
            self.items_list.clear()
            self.empty_message.setVisible(True)
            self.items_list.setVisible(False)
    
    def get_time_display(self, item_text):
        """클립보드 항목의 경과 시간 표시 형식 반환"""
        current_time = time.time()
        if item_text not in self.clipboard_times:
            self.clipboard_times[item_text] = current_time
        
        elapsed_seconds = current_time - self.clipboard_times[item_text]
        
        if elapsed_seconds < 60:
            return "방금 전"
        elif elapsed_seconds < 60 * 60:
            minutes = int(elapsed_seconds / 60)
            return f"{minutes}분 전"
        elif elapsed_seconds < 60 * 60 * 24:
            hours = int(elapsed_seconds / (60 * 60))
            return f"{hours}시간 전"
        else:
            days = int(elapsed_seconds / (60 * 60 * 24))
            return f"{days}일 전"
    
    def get_item_icon(self, item_text):
        """클립보드 항목 유형에 따른 아이콘 반환"""
        size = 24
        text_icon = QPixmap(size, size)
        text_icon.fill(Qt.GlobalColor.transparent)
        painter = QPainter(text_icon)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # 아이템 유형 감지
        is_link = item_text.startswith(('http://', 'https://', 'www.'))
        is_code = item_text.startswith(('{"', '[{', '<?xml', '<html', '<!DOCTYPE', 'function', 'class', 'def ', 'import ', 'from '))
        is_email = '@' in item_text and '.' in item_text.split('@')[1] and not is_link
        is_number = all(c.isdigit() or c in ',.+-*/() ' for c in item_text.strip()) and any(c.isdigit() for c in item_text)
        
        # 아이콘 배경색 및 텍스트 결정
        if is_link:
            bg_color = QColor("#4285F4")  # Google 블루
            icon_text = "🔗"
        elif is_code:
            bg_color = QColor("#0F9D58")  # Google 그린
            icon_text = "{"
        elif is_email:
            bg_color = QColor("#DB4437")  # Google 레드
            icon_text = "✉"
        elif is_number:
            bg_color = QColor("#F4B400")  # Google 옐로우
            icon_text = "#"
        else:
            bg_color = QColor(COLOR_PRIMARY)
            icon_text = "T"
        
        # 원형 아이콘 그리기
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(0, 0, size, size)
        
        # 아이콘 텍스트 그리기
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, icon_text)
        
        painter.end()
        return text_icon
    
    def truncate_text(self, text, max_len):
        """긴 텍스트 잘라내기 (줄바꿈 유지 시도)"""
        if not text:
            return ""
        
        # 줄바꿈을 유지하되, 전체적인 길이 제한은 적용.
        # 앞뒤 공백/줄바꿈 제거
        processed_text = text.strip()
        
        if len(processed_text) > max_len:
            # max_len까지 자르고, 마지막이 잘린 단어의 일부가 아니도록 공백이나 줄바꿈에서 자르려고 시도 (선택적 개선)
            # 간단하게는 그냥 자름
            return processed_text[:max_len-3] + "..."
        return processed_text
    
    def create_item_widget(self, item_text, index):
        """클립보드 항목을 표시할 위젯 생성 - 새로운 가로형 디자인"""
        # 전체 아이템 컨테이너
        item_widget = QFrame()
        item_widget.setProperty("customItem", True)
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(10, 8, 10, 8)
        item_layout.setSpacing(10)
        
        # 아이콘 영역
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_pixmap = self.get_item_icon(item_text)
        icon_label.setPixmap(icon_pixmap)
        
        # 내용 영역 (메인)
        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        
        # 텍스트 레이블
        text_label = QLabel(self.truncate_text(item_text, CLIP_PREVIEW_MAX_LEN))
        text_label.setWordWrap(False)
        text_label.setTextFormat(Qt.TextFormat.PlainText)
        
        # 시간 표시 레이블
        time_label = QLabel(self.get_time_display(item_text))
        time_label.setObjectName("timeLabel")
        time_label.setStyleSheet("color: rgba(128, 128, 128, 180); font-size: 9pt;")
        time_label.setFixedWidth(70) # 시간 레이블 고정 폭
        
        # URL인 경우 링크 버튼 추가
        url_match = re.search(r'https?://\S+', item_text)
        open_link_button = None
        if url_match:
            open_link_button = QToolButton()
            open_link_button.setObjectName("openLinkButton")
            open_link_button.setText("🔗")
            open_link_button.setToolTip("링크 열기")
            open_link_button.setFixedSize(24, 24)
            open_link_button.clicked.connect(lambda: self._open_url(url_match.group(0)))
        
        # 내용 영역에 추가
        content_layout.addWidget(text_label, 1)  # stretch factor 1
        
        # 아이템 레이아웃에 추가
        item_layout.addWidget(icon_label)
        item_layout.addWidget(content_area, 1)  # stretch factor 1
        item_layout.addWidget(time_label)
        if open_link_button:
            item_layout.addWidget(open_link_button)
        
        # 배경 스타일 설정
        bg_color = "#2D2D2D" if self.dark_mode else "white"
        hover_color = "#323232" if self.dark_mode else "#F5F5F5"
        border_color = "#444" if self.dark_mode else "#E0E0E0"
        
        item_widget.setStyleSheet(f"""
            QFrame[customItem=true] {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            
            QFrame[customItem=true]:hover {{
                background-color: {hover_color};
                border: 1px solid {COLOR_PRIMARY};
            }}
            
            QToolButton#openLinkButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
                font-size: 12pt;
            }}
            
            QToolButton#openLinkButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.15)' if self.dark_mode else 'rgba(0, 0, 0, 0.08)'};
            }}
        """)
        
        return item_widget
    
    def filter_history(self, search_term=""):
        """검색어에 따라 클립보드 히스토리 필터링"""
        self.search_text = search_term.lower()
        
        # 현재 카테고리에 해당하는 항목 필터링
        if self.current_category == 0:  # 클립보드 히스토리
            if not self.current_history_items:
                print("클립보드 히스토리 항목 없음")
                self.filtered_items = []
            else:
                print(f"필터링: {len(self.current_history_items)}개 항목 중 '{self.search_text}' 검색")
                self.filtered_items = [item for item in self.current_history_items 
                                      if self.search_text in item.lower()]
        
        # 필터링 결과 업데이트
        self.update_displayed_items()
    
    def update_displayed_items(self):
        """현재 필터링된 아이템을 화면에 표시"""
        self.items_list.clear()
        
        if not self.filtered_items:
            self.empty_message.setVisible(True)
            return
        
        self.empty_message.setVisible(False)
        
        for i, item_text in enumerate(self.filtered_items):
            # 아이템 위젯 생성
            item_widget = self.create_item_widget(item_text, i)
            
            # QListWidgetItem 생성 및 설정
            list_item = QListWidgetItem(self.items_list)
            list_item.setSizeHint(item_widget.sizeHint())
            self.items_list.setItemWidget(list_item, item_widget)
            list_item.setData(Qt.ItemDataRole.UserRole, item_text)
        
        # 첫 번째 아이템 선택
        if self.items_list.count() > 0:
            self.items_list.setCurrentRow(0)
    
    def on_item_clicked(self, item):
        """클립보드 항목 클릭 처리"""
        item_text = item.data(Qt.ItemDataRole.UserRole)
        print(f"항목 클릭: {item_text[:30]}... - 붙여넣기 요청")
        
        self.hide_popup() # 먼저 팝업을 숨기기 시작
        
        # 팝업이 닫힐 시간을 고려하여 약간의 지연 후 복사/붙여넣기 실행
        # 애니메이션 시간 (100ms) + 추가 버퍼
        QTimer.singleShot(200, lambda t=item_text: self._execute_copy_paste_action(t))
    
    def _execute_copy_paste_action(self, text_to_paste):
        """지연 후 실제 클립보드 복사 및 붙여넣기 실행"""
        try:
            print(f"지연 후 작업 실행: {text_to_paste[:30]}...")
            
            # 1. 클립보드에 복사
            self.set_clipboard_with_retry(text_to_paste)
            # pyperclip.paste() 등으로 확인 로그는 set_clipboard_with_retry 내부에 이미 있음

            # 2. 클립보드 히스토리 수동 추가 (필요한 경우)
            #    set_clipboard_with_retry가 성공하면 ClipboardMonitorThread가 자동으로 감지할 가능성이 높음.
            #    중복 추가를 피하려면 아래 줄은 주석 처리하거나, add_item_manually 내부에서 중복 방지 로직 필요.
            # ClipboardMonitorThread.add_item_manually(text_to_paste, set_clipboard=False)
            
            # 3. 붙여넣기 실행
            self.execute_paste() # 이 함수 내부에 최종 time.sleep(0.3) 있음
            print("붙여넣기 작업 완료.")
            
        except Exception as e:
            print(f"붙여넣기 작업 중 오류 (_execute_copy_paste_action): {e}")
            traceback.print_exc()

    def set_clipboard_with_retry(self, text, max_retries=5):
        """재시도 로직으로 클립보드 설정"""
        print(f"클립보드에 텍스트 복사 시도: {text[:30]}...")
        retry_count = 0
        last_error = None
        while retry_count < max_retries:
            try:
                QApplication.clipboard().setText(text)
                print(f"Qt 클립보드 설정 성공 (시도 {retry_count+1})")
                return
            except Exception as e:
                print(f"Qt 클립보드 설정 실패 (시도 {retry_count+1}): {e}")
                last_error = e
                retry_count += 1
                time.sleep(0.1)
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                pyperclip.copy(text)
                print(f"pyperclip 설정 성공 (시도 {retry_count+1})")
                return
            except Exception as e:
                print(f"pyperclip 설정 실패 (시도 {retry_count+1}): {e}")
                last_error = e
                retry_count += 1
                time.sleep(0.2)
        
        print("모든 클립보드 설정 시도 실패")
        if last_error:
            # raise last_error # 여기서 바로 에러를 발생시키기 보다 실패를 알리는게 나을수도
            print(f"클립보드 설정 최종 실패: {last_error}")

    def execute_paste(self):
        """여러 방법으로 붙여넣기 시도"""
        time.sleep(0.3) # 실제 붙여넣기 전 약간의 최종 지연
        try:
            if sys.platform == "win32":
                self.try_windows_paste_methods()
            else:
                self.try_pynput_paste()
        except Exception as e:
            print(f"붙여넣기 실행 오류: {e}")
            traceback.print_exc()

    def try_windows_paste_methods(self):
        """Windows 환경에서 여러 붙여넣기 방법 시도"""
        print("Windows 붙여넣기 시도 중...")
        try:
            print("방법 1: Windows SendInput API 사용...")
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            class KeyBdInput(ctypes.Structure): _fields_ = [("wVk", wintypes.WORD),("wScan", wintypes.WORD),("dwFlags", wintypes.DWORD),("time", wintypes.DWORD),("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]
            class MouseInput(ctypes.Structure): _fields_ = [("dx", wintypes.LONG),("dy", wintypes.LONG),("mouseData", wintypes.DWORD),("dwFlags", wintypes.DWORD),("time", wintypes.DWORD),("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]
            class HardwareInput(ctypes.Structure): _fields_ = [("uMsg", wintypes.DWORD),("wParamL", wintypes.WORD),("wParamH", wintypes.WORD)]
            class InputUnion(ctypes.Union): _fields_ = [("ki", KeyBdInput),("mi", MouseInput),("hi", HardwareInput)]
            class Input(ctypes.Structure): _fields_ = [("type", wintypes.DWORD),("ii", InputUnion)]
            INPUT_KEYBOARD, KEYEVENTF_KEYUP, VK_CONTROL, VK_V = 1, 0x0002, 0x11, 0x56
            inputs = (Input * 4)(
                Input(INPUT_KEYBOARD, InputUnion(ki=KeyBdInput(VK_CONTROL, 0, 0, 0, None))),
                Input(INPUT_KEYBOARD, InputUnion(ki=KeyBdInput(VK_V, 0, 0, 0, None))),
                Input(INPUT_KEYBOARD, InputUnion(ki=KeyBdInput(VK_V, 0, KEYEVENTF_KEYUP, 0, None))),
                Input(INPUT_KEYBOARD, InputUnion(ki=KeyBdInput(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, None)))
            )
            time.sleep(0.1)
            # print("SendInput API 호출 전 추가 지연 완료 (0.1초)") # 로그 간소화
            result = user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(Input))
            if result != 4: print(f"SendInput 실패: {ctypes.get_last_error()}"); raise Exception("SendInput failed")
            else: print("SendInput 성공!"); return
        except Exception as e: print(f"방법 1 실패: {e}")
        try:
            print("방법 2: Windows keybd_event API 사용...")
            import ctypes # 중복 import지만, 각 try 블록 독립성 위해 유지
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            KEYEVENTF_KEYUP, VK_CONTROL, VK_V = 0x0002, 0x11, 0x56
            time.sleep(0.1)
            # print("keybd_event API 호출 전 추가 지연 완료 (0.1초)") # 로그 간소화
            user32.keybd_event(VK_CONTROL, 0, 0, 0); time.sleep(0.05)
            user32.keybd_event(VK_V, 0, 0, 0); time.sleep(0.05)
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0); time.sleep(0.05)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            print("keybd_event 성공!"); return
        except Exception as e: print(f"방법 2 실패: {e}")
        self.try_pynput_paste()

    def try_pynput_paste(self):
        """pynput 키보드 컨트롤러로 붙여넣기 시도"""
        print("방법 3: pynput 키보드 컨트롤러 사용...")
        try:
            keyboard_controller = KeyboardController()
            paste_key = Key.cmd if sys.platform == "darwin" else Key.ctrl
            keyboard_controller.press(paste_key); time.sleep(0.05)
            keyboard_controller.press('v'); time.sleep(0.05)
            keyboard_controller.release('v'); time.sleep(0.05)
            keyboard_controller.release(paste_key)
            print("pynput 방식 성공!")
        except Exception as e: 
            print(f"방법 3 실패: {e}")
            print("모든 붙여넣기 방법이 실패했습니다. 사용자에게 수동 붙여넣기 안내...")

    def show_popup_animated(self):
        """애니메이션과 함께 팝업 표시"""
        try:
            animation_active = self.animation.state() == QPropertyAnimation.State.Running
            if self.isVisible() and abs(self.opacity_effect.opacity() - 1.0) < 0.01 and not animation_active:
                return 
            if animation_active and self.animation.direction() == QPropertyAnimation.Direction.Forward:
                return 
            if animation_active and self.animation.direction() == QPropertyAnimation.Direction.Backward:
                print("숨김 애니메이션을 표시 애니메이션으로 전환합니다.")
                self.animation.stop()
                self.animation.setDirection(QPropertyAnimation.Direction.Forward)
                try: self.animation.finished.disconnect() 
                except TypeError: pass
                self.animation.start()
                return

            self.change_category(0) 
            self.search_box.clear()
            
            target_screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            screen_geometry = target_screen.availableGeometry()
            
            # 화면 하단 전체를 채우는 형태로 설정
            window_width = screen_geometry.width()
            window_height = int(screen_geometry.height() * 0.30)  # 화면 높이의 30%
            
            # 창 위치를 화면 하단으로 설정
            x = screen_geometry.x()
            y = screen_geometry.bottom() - window_height
            
            self.resize(window_width, window_height)
            self.move(x, y)
            
            self.animation.stop()
            self.opacity_effect.setOpacity(0.0)
            self.show()
            self.activateWindow()
            self.raise_()
            
            try: self.animation.finished.disconnect() 
            except TypeError: pass
            
            self.animation.setDirection(QPropertyAnimation.Direction.Forward)
            self.animation.start()
            QTimer.singleShot(100, self.search_box.setFocus)
        except Exception as e:
            print(f"팝업 표시 오류: {e}")
            traceback.print_exc()
            
    def hide_popup(self):
        """애니메이션과 함께 팝업 숨기기 (일반용)"""
        animation_active = self.animation.state() == QPropertyAnimation.State.Running
        
        if not self.isVisible() or abs(self.opacity_effect.opacity() - 0.0) < 0.01:
            # print("팝업 이미 숨겨져 있음")
            # 붙여넣기 관련 즉시 실행 로직 제거
            return

        if animation_active and self.animation.direction() == QPropertyAnimation.Direction.Backward:
            # print("이미 숨김 애니메이션 진행 중")
            return

        if animation_active and self.animation.direction() == QPropertyAnimation.Direction.Forward:
            print("표시 애니메이션을 숨김 애니메이션으로 전환합니다.")
            self.animation.stop()
            self.animation.setDirection(QPropertyAnimation.Direction.Backward)
            # 콜백은 이 함수 하단에서 일반용으로 (재)연결됨
            self.animation.start()
            return

        # print("정상적인 숨김 애니메이션 시작...")
        self.animation.stop()
        self.animation.setDirection(QPropertyAnimation.Direction.Backward)
        
        # 일반 숨김 애니메이션 완료 콜백 연결 (항상)
        try: 
            self.animation.finished.disconnect(self._on_hide_animation_finished)
        except TypeError: pass # 연결 안되어 있었으면 무시
        self.animation.finished.connect(self._on_hide_animation_finished)

        self.animation.start()
    
    def _on_hide_animation_finished(self):
        """숨김 애니메이션 완료 후 처리 (일반적인 숨김, 붙여넣기 목적 아님)"""
        # 이 콜백은 붙여넣기가 아닌 일반적인 숨김 완료 시에만 호출되어야 함
        # 확인: 현재 opacity가 startValue(0.0)에 가까운지 확인
        if self.animation.direction() == QPropertyAnimation.Direction.Backward and \
           abs(self.opacity_effect.opacity() - self.animation.startValue()) < 0.01:
            # print("일반 숨김 애니메이션 완료.") # 로그 간소화
            self.hide()
            
        try:
            self.animation.finished.disconnect(self._on_hide_animation_finished)
        except TypeError:
            pass # 연결되지 않은 경우 오류 무시
    
    def update_history(self, history_items):
        """클립보드 히스토리 업데이트"""
        self.current_history_items = list(history_items)
        self.filter_history(self.search_box.text())

    def open_settings(self):
        """설정 다이얼로그 열기"""
        # 부모 애플리케이션의 open_settings_dialog 메서드 호출을 위해 시그널 발생
        self.hide_popup()  # 팝업 숨기기
        # 창 부모를 통해 설정 다이얼로그 호출
        parent = self.parent()
        # 부모를 찾을 수 없는 경우 QApplication.instance()를 통해 시도
        if parent is None:
            app = QApplication.instance()
            # 모든 최상위 위젯을 순회하며 ClipboardManagerApp 찾기
            for widget in app.topLevelWidgets():
                if hasattr(widget, 'open_settings_dialog'):
                    widget.open_settings_dialog()
                    return
            # 못 찾은 경우 직접 다이얼로그 열기
            from config_manager import load_config, DEFAULT_HOTKEY_CONFIG
            config = load_config()
            current_conf = config.get("hotkey", DEFAULT_HOTKEY_CONFIG).copy()
            settings_dialog = SettingsDialog(current_conf)
            settings_dialog.exec()
        else:
            # 부모가 ClipboardManagerApp인 경우
            if hasattr(parent, 'open_settings_dialog'):
                parent.open_settings_dialog()

# --- Settings Dialog ---
class SettingsDialog(QDialog):
    """
    설정 대화상자 클래스
    모던한 디자인의 새로운 UI
    """
    hotkey_updated = pyqtSignal(dict)
    update_hotkey_display_signal = pyqtSignal(str)
    
    def __init__(self, current_hotkey_config, parent=None):
        """초기화 함수"""
        super().__init__(parent)
        self.setWindowTitle("UniPaste 설정")
        self.setMinimumSize(450, 350)
        self.current_hotkey_config = current_hotkey_config.copy()
        self.temp_hotkey_config = None
        
        # 시스템 테마 감지
        palette = QApplication.palette()
        window_color = palette.color(QPalette.ColorRole.Window)
        self.dark_mode = window_color.lightness() < 128
        
        self._recording_listener_thread = None
        
        self.init_ui()
        self.apply_styles()
    
    def init_ui(self):
        """UI 요소 초기화 및 배치"""
        # 메인 레이아웃
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # 타이틀
        title_label = QLabel("UniPaste 설정")
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)
        
        # 구분선
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setObjectName("separator")
        layout.addWidget(separator)
        
        # 섹션: 단축키 설정
        hotkey_section = QFrame()
        hotkey_section.setObjectName("sectionFrame")
        hotkey_layout = QVBoxLayout(hotkey_section)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_layout.setSpacing(15)
        
        # 섹션 제목
        section_title = QLabel("단축키 설정")
        section_title.setObjectName("sectionTitle")
        hotkey_layout.addWidget(section_title)
        
        # 설명 텍스트
        description = QLabel("클립보드 히스토리를 열기 위한 단축키를 설정합니다.")
        description.setObjectName("description")
        description.setWordWrap(True)
        hotkey_layout.addWidget(description)
        
        # 현재 단축키 표시
        hotkey_display_layout = QHBoxLayout()
        hotkey_label = QLabel("현재 단축키:")
        hotkey_label.setObjectName("fieldLabel")
        self.hotkey_display = QLineEdit()
        self.hotkey_display.setObjectName("hotkeyDisplay")
        self.hotkey_display.setReadOnly(True)
        self.hotkey_display.setText(format_hotkey_for_display(self.current_hotkey_config))
        self.hotkey_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        hotkey_display_layout.addWidget(hotkey_label)
        hotkey_display_layout.addWidget(self.hotkey_display, 1)  # 1은 stretch factor
        hotkey_layout.addLayout(hotkey_display_layout)
        
        # 단축키 기록 버튼
        self.record_button = QPushButton("단축키 기록")
        self.record_button.setObjectName("recordButton")
        self.record_button.clicked.connect(self.start_hotkey_recording)
        hotkey_layout.addWidget(self.record_button)
        
        # 상태 메시지
        self.status_label = QLabel("버튼을 누르고 새 단축키를 입력하세요")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hotkey_layout.addWidget(self.status_label)
        
        # 단축키 섹션 추가
        layout.addWidget(hotkey_section)
        
        # 일반 설정 영역
        general_section = QFrame()
        general_section.setObjectName("sectionFrame")
        general_layout = QVBoxLayout(general_section)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(15)
        
        # 섹션 제목
        general_title = QLabel("일반 설정")
        general_title.setObjectName("sectionTitle")
        general_layout.addWidget(general_title)
        
        # 테마 설정
        theme_layout = QHBoxLayout()
        theme_label = QLabel("테마:")
        theme_label.setObjectName("fieldLabel")
        
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themeCombo")
        self.theme_combo.addItems(["시스템 기본값", "라이트 모드", "다크 모드"])
        
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo, 1)
        general_layout.addLayout(theme_layout)
        
        # 자동 시작 설정
        self.autostart_check = QCheckBox("시스템 시작 시 자동 실행")
        self.autostart_check.setObjectName("autostartCheck")
        general_layout.addWidget(self.autostart_check)
        
        # 설정 섹션 추가
        layout.addWidget(general_section)
        
        # 여백 추가
        layout.addStretch()
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.save_button = QPushButton("저장")
        self.save_button.setObjectName("saveButton")
        self.save_button.clicked.connect(self.save_settings)
        
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        # 단축키 표시 시그널 연결
        self.update_hotkey_display_signal.connect(self.hotkey_display.setText)
    
    def apply_styles(self):
        """스타일시트 적용"""
        # 테마에 따른 색상 설정
        if self.dark_mode:
            bg_color = "#1E1E1E"
            text_color = "#EFEFEF"
            title_color = "#FFFFFF"
            border_color = "#444"
            input_bg = "#333"
            button_bg = COLOR_PRIMARY
            button_text = "white"
            button_hover = "#0069C0"
            separator_color = "#555"
        else:
            bg_color = "#F9F9F9"
            text_color = "#333333"
            title_color = "#111111"
            border_color = "#E0E0E0"
            input_bg = "white"
            button_bg = COLOR_PRIMARY
            button_text = "white"
            button_hover = "#0069C0"
            separator_color = "#E0E0E0"
        
        # 스타일시트 적용
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                font-family: {FONT_MAIN};
                color: {text_color};
                border-radius: 10px;
            }}
            
            #titleLabel {{
                font-size: 22px;
                font-weight: bold;
                color: {title_color};
            }}
            
            #separator {{
                background-color: {separator_color};
                max-height: 1px;
            }}
            
            #sectionTitle {{
                font-size: 16px;
                font-weight: bold;
                color: {title_color};
            }}
            
            #sectionFrame {{
                background-color: {'rgba(255, 255, 255, 0.05)' if self.dark_mode else 'rgba(0, 0, 0, 0.02)'};
                border-radius: 8px;
                padding: 15px;
                border: 1px solid {border_color};
            }}
            
            #description, #fieldLabel, #statusLabel {{
                color: {'#BBB' if self.dark_mode else '#555'};
            }}
            
            #hotkeyDisplay, QComboBox {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 5px;
                padding: 8px;
                color: {text_color};
            }}
            
            #hotkeyDisplay:focus, QComboBox:focus {{
                border: 1px solid {COLOR_PRIMARY};
            }}
            
            QPushButton {{
                background-color: {'rgba(255, 255, 255, 0.1)' if self.dark_mode else 'rgba(0, 0, 0, 0.05)'};
                border: 1px solid {border_color};
                border-radius: 5px;
                padding: 10px 15px;
                color: {text_color};
            }}
            
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.15)' if self.dark_mode else 'rgba(0, 0, 0, 0.08)'};
            }}
            
            #saveButton, #recordButton {{
                background-color: {button_bg};
                color: {button_text};
                border: none;
                font-weight: bold;
            }}
            
            #saveButton:hover, #recordButton:hover {{
                background-color: {button_hover};
            }}
            
            #cancelButton {{
                background-color: {'rgba(255, 255, 255, 0.1)' if self.dark_mode else 'rgba(0, 0, 0, 0.05)'};
                border: 1px solid {border_color};
            }}
            
            QCheckBox {{
                color: {text_color};
                spacing: 5px;
            }}
            
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid {border_color};
                background-color: {input_bg};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {COLOR_PRIMARY};
                border: 1px solid {COLOR_PRIMARY};
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
            }}
        """)
    
    def start_hotkey_recording(self):
        """단축키 기록 시작"""
        self.status_label.setText("새 단축키를 입력하세요... (ESC로 취소)")
        self.record_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.temp_hotkey_config = None
        
        if self._recording_listener_thread and self._recording_listener_thread.isRunning():
            self._recording_listener_thread.stop_listener_and_quit()
            self._recording_listener_thread.wait()
            
        self._recording_listener_thread = HotkeyRecordingThread(self)
        self._recording_listener_thread.key_combination_recorded.connect(self.on_key_combination_recorded)
        self._recording_listener_thread.recording_canceled.connect(self.on_recording_canceled)
        self._recording_listener_thread.update_display_signal.connect(self.update_hotkey_display_from_thread)
        self._recording_listener_thread.start()
    
    @pyqtSlot(str)
    def update_hotkey_display_from_thread(self, text):
        """스레드로부터 단축키 표시 업데이트 요청 처리"""
        self.hotkey_display.setText(text)
    
    @pyqtSlot(list, str)
    def on_key_combination_recorded(self, modifiers, main_key):
        """단축키 조합 기록 완료 처리"""
        self.temp_hotkey_config = {"modifiers": modifiers, "key": main_key}
        display_text = format_hotkey_for_display(self.temp_hotkey_config)
        self.status_label.setText(f"기록된 단축키: {display_text}")
        self.record_button.setEnabled(True)
        self.save_button.setEnabled(True)
        
        if self._recording_listener_thread:
            self._recording_listener_thread.quit()
            self._recording_listener_thread.wait()
            self._recording_listener_thread = None
    
    @pyqtSlot()
    def on_recording_canceled(self):
        """단축키 기록 취소 처리"""
        self.status_label.setText("단축키 기록이 취소되었습니다.")
        self.hotkey_display.setText(format_hotkey_for_display(self.current_hotkey_config))
        self.record_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.temp_hotkey_config = None
        
        if self._recording_listener_thread:
            self._recording_listener_thread.quit()
            self._recording_listener_thread.wait()
            self._recording_listener_thread = None
    
    def save_settings(self):
        """설정 저장"""
        # 단축키 설정 저장
        if self.temp_hotkey_config and self.temp_hotkey_config.get("key"):
            self.current_hotkey_config = self.temp_hotkey_config.copy()
        
        # 기본 단축키가 설정되지 않은 경우 기본값 사용
        if not self.current_hotkey_config or not self.current_hotkey_config.get("key"):
            from config_manager import DEFAULT_HOTKEY_CONFIG
            self.current_hotkey_config = DEFAULT_HOTKEY_CONFIG.copy()
            self.hotkey_display.setText(format_hotkey_for_display(self.current_hotkey_config))
            
        # 설정 저장
        from config_manager import load_config, save_config
        config_data = load_config()
        config_data["hotkey"] = self.current_hotkey_config
        save_config(config_data)
        
        # 단축키 변경 시그널 발생
        self.hotkey_updated.emit(self.current_hotkey_config.copy())
        self.accept()
    
    def reject(self):
        """대화상자 취소"""
        if self._recording_listener_thread and self._recording_listener_thread.isRunning():
            self._recording_listener_thread.stop_listener_and_quit()
            self._recording_listener_thread.wait()
        super().reject()
    
    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        self.reject()
        super().closeEvent(event) 
import customtkinter as ctk
import os
import sys
import uuid
import hashlib
import logging
from datetime import datetime
import tkinter
import tkinter.font as tkfont
from tkinter import colorchooser
import media_utils  # 미디어 유틸리티 모듈 임포트
from data_manager import DataManager  # 데이터 관리 모듈 임포트
import exporter  # 내보내기 모듈 임포트
import dialogs  # 다이얼로그 모듈 임포트
from paint_app import PaintFrame # 그림판 모듈 임포트
from table_widget import TableWidget # 표 위젯 모듈 임포트
from ui_colors import UI_COLORS, PASTEL_COLORS, MEMO_LIST_COLORS # 색상 팔레트 임포트

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 줄 번호 위젯 ---
class LineNumbers(tkinter.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text_widget = None

    def attach(self, text_widget):
        self.text_widget = text_widget

    def redraw(self, *args):
        """줄 번호 다시 그리기"""
        self.delete("all")
        if not self.text_widget:
            return

        i = self.text_widget.index("@0,0")
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.create_text(40, y, anchor="ne", text=linenum, fill="#7F7F7F", font=("Roboto Medium", 14))
            i = self.text_widget.index(f"{i}+1line")

# 설정
ctk.set_appearance_mode("Dark")  # 모드: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # 테마: "blue" (standard), "green", "dark-blue"

DATA_FILE = "memos.json"
SETTINGS_FILE = "settings.json"

def get_base_dir():
    """애플리케이션 기본 디렉토리 반환 (PyInstaller 호환)"""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 패키징된 경우
        return sys._MEIPASS
    else:
        # 일반 Python 실행
        return os.path.dirname(os.path.abspath(__file__))

def get_resource_dir(subdir):
    """리소스 디렉토리 경로 반환 (자동 생성)"""
    base = get_base_dir()
    resource_path = os.path.join(base, subdir)
    try:
        if not os.path.exists(resource_path):
            os.makedirs(resource_path)
    except OSError as e:
        logger.error(f"Failed to create resource directory {resource_path}: {e}")
    return resource_path

class MemoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Under Memo")
        self.geometry("900x600")

        # 플랫폼 감지 (단축키에 사용)
        import platform
        self._platform = platform.system().lower()

        # 데이터 초기화
        self.memos = {}  # {uuid: {title, content, timestamp, tags, pinned, locked, password}}
        self.current_memo_id = None
        self.save_timer = None
        self.ui_update_timer = None  # UI 업데이트 디바운싱용
        self.paint_frames = [] # PaintFrame 객체 참조 유지용 리스트
        self.table_widgets = [] # TableWidget 객체 참조 유지용 리스트
        self._content_cache = None  # 직렬화 캐시

        # 데이터 매니저 초기화
        self.data_manager = DataManager(DATA_FILE, SETTINGS_FILE)
        self.is_modified = False  # 현재 메모가 수정되었는지 여부
        self.memo_buttons = {}  # 메모 ID별 버튼 저장 (색상 업데이트용)
        self.search_mode = False  # 검색 모드 여부
        self.pin_filter_active = False  # 고정된 메모만 보기 필터 상태
        self.load_memos()

        # 현재 입력 서식 상태 추적
        self.drag_data = {"id": None, "start_y": 0, "is_dragging": False, "was_dragging": False}  # 드래그 상태 데이터
        self._configured_font_tags = set()  # 최적화: 이미 설정된 폰트 태그 캐싱
        self.current_input_tags = set()  # 커서 위치에서 적용할 태그들
        self.manual_format_mode = False  # 사용자가 수동으로 서식을 설정했는지 여부
        self.always_on_top = False  # 창 고정 상태

        # 그리드 레이아웃 설정 (1x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 좌측 사이드바 (메모 목록) ===
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # 상단 컨트롤 프레임 (검색 + 항상 위)
        self.top_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.top_control_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.top_control_frame.grid_columnconfigure(0, weight=1)

        # 검색 바
        self.search_entry = ctk.CTkEntry(
            self.top_control_frame,
            placeholder_text="🔍 Search memos...",
            height=35
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # 항상 위 고정 버튼
        self.always_on_top_button = ctk.CTkButton(
            self.top_control_frame,
            text="📌",
            width=35,
            height=35,
            fg_color="transparent",
            command=self.toggle_always_on_top
        )
        self.always_on_top_button.grid(row=0, column=1)

        # 새 메모 & 고정 필터 프레임
        self.new_memo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.new_memo_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.new_memo_frame.grid_columnconfigure(0, weight=1)

        # 새 메모 버튼
        self.new_button = ctk.CTkButton(
            self.new_memo_frame,
            text="+ New Memo",
            command=self.create_new_memo,
            fg_color=PASTEL_COLORS["primary"],
            hover_color="#64B5F6",
            text_color="white",
            height=35
        )
        self.new_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # 고정된 메모만 보기 버튼
        self.pin_filter_button = ctk.CTkButton(
            self.new_memo_frame,
            text="⭐",
            width=35,
            height=35,
            command=self.toggle_pin_filter,
            fg_color=PASTEL_COLORS["accent"],
            hover_color="#FFB74D",
            text_color="white"
        )
        self.pin_filter_button.grid(row=0, column=1)

        # 기능 버튼 프레임 (잠금, 삭제만)
        self.action_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.action_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.action_frame.grid_columnconfigure((0, 1), weight=1)

        # 잠금 버튼
        self.lock_button = ctk.CTkButton(
            self.action_frame,
            text="🔒 Lock",
            height=30,
            command=self.toggle_lock,
            fg_color=PASTEL_COLORS["secondary"],
            hover_color="#90A4AE",
            text_color="white"
        )
        self.lock_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # 삭제 버튼
        self.delete_button = ctk.CTkButton(
            self.action_frame,
            text="🗑 Delete",
            height=30,
            fg_color=PASTEL_COLORS["danger"],
            hover_color="#E57373",
            command=self.delete_memo,
            text_color="white"
        )
        self.delete_button.grid(row=0, column=1, sticky="ew")

        # 태그 프레임
        self.tag_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.tag_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.tag_entry = ctk.CTkEntry(
            self.tag_frame,
            placeholder_text="Add tag...",
            height=25
        )
        self.tag_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.tag_entry.bind("<Return>", self.add_tag)

        # 태그 관리 버튼
        self.manage_tags_button = ctk.CTkButton(
            self.tag_frame,
            text="📝",
            width=25,
            height=25,
            command=self.manage_tags
        )
        self.manage_tags_button.grid(row=0, column=1)

        self.tag_frame.grid_columnconfigure(0, weight=1)

        # 투명도 조절 프레임
        self.opacity_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.opacity_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.opacity_label = ctk.CTkLabel(self.opacity_frame, text="Opacity", font=("Roboto Medium", 12))
        self.opacity_label.pack(side="left", padx=(0, 10))

        self.opacity_slider = ctk.CTkSlider(
            self.opacity_frame,
            from_=0.3,
            to=1.0,
            number_of_steps=70,
            command=self.change_opacity,
            width=100,
            height=15
        )
        self.opacity_slider.pack(side="left", fill="x", expand=True)
        self.opacity_slider.set(1.0)

        # 메모 리스트 (스크롤 가능)
        self.scrollable_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="Memos")
        self.scrollable_frame.grid(row=5, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # macOS에서 스크롤 활성화: Canvas에 포커스 설정
        # macOS는 MouseWheel 이벤트를 발생시키지 않고, 포커스된 Canvas를 자동 스크롤함
        if hasattr(self.scrollable_frame, '_parent_canvas'):
            canvas = self.scrollable_frame._parent_canvas

            # Canvas가 포커스를 받을 수 있도록 설정
            canvas.configure(takefocus=1)

            # Frame에 마우스가 들어오면 Canvas에 포커스
            self.scrollable_frame.bind("<Enter>", lambda _: canvas.focus_set())

        # === 우측 메인 (텍스트 에디터) ===
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # === 서식 툴바 ===
        self.toolbar_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=40)
        self.toolbar_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 10))

        # 그룹 1: 텍스트 서식 (폰트, 크기, 스타일, 색상)
        self.text_format_group = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.text_format_group.pack(side="left", padx=(0, 15))

        # 1. 폰트 선택
        self.fonts = list(tkfont.families())
        self.fonts.sort()
        self.font_var = ctk.StringVar(value="Roboto Medium")
        self.font_combo = ctk.CTkComboBox(
            self.text_format_group, values=self.fonts, variable=self.font_var, width=150,
            command=self.change_font_family
        )
        self.font_combo.pack(side="left", padx=(0, 5))

        # 2. 사이즈 선택
        self.sizes = [str(s) for s in range(8, 40, 2)]
        self.size_var = ctk.StringVar(value="16")
        self.size_combo = ctk.CTkComboBox(
            self.text_format_group, values=self.sizes, variable=self.size_var, width=70,
            command=self.change_font_size
        )
        self.size_combo.pack(side="left", padx=(0, 10))

        # 3. 스타일 버튼들 (B, I, U, S)
        self.bold_button = ctk.CTkButton(
            self.text_format_group,
            text="B",
            font=("Roboto Medium", 14, "bold"),
            width=30, height=30,
            fg_color=UI_COLORS["text_format"],
            command=self.toggle_bold
        )
        self.bold_button.pack(side="left", padx=(0, 5))

        self.italic_button = ctk.CTkButton(
            self.text_format_group,
            text="I",
            font=("Roboto Medium", 14, "italic"),
            width=30, height=30,
            fg_color=UI_COLORS["text_format"],
            command=self.toggle_italic
        )
        self.italic_button.pack(side="left", padx=(0, 5))

        self.underline_button = ctk.CTkButton(
            self.text_format_group,
            text="U",
            font=("Roboto Medium", 14, "underline"),
            width=30, height=30,
            fg_color=UI_COLORS["text_format"],
            command=self.toggle_underline
        )
        self.underline_button.pack(side="left", padx=(0, 5))

        self.strike_button = ctk.CTkButton(
            self.text_format_group,
            text="S",
            font=("Roboto Medium", 14, "overstrike"),
            width=30, height=30,
            fg_color=UI_COLORS["text_format"],
            command=self.toggle_overstrike
        )
        self.strike_button.pack(side="left", padx=(0, 10))

        # 4. 색상 버튼
        self.color_button = ctk.CTkButton(
            self.text_format_group, text="Color", width=60, height=30, fg_color=UI_COLORS["text_format"], command=self.change_color
        )
        self.color_button.pack(side="left", padx=(0, 5))

        # 5. 하이라이트 버튼
        self.highlight_button = ctk.CTkButton(
            self.text_format_group, text="Highlight", width=80, height=30, fg_color=UI_COLORS["accent"], command=self.change_highlight
        )
        self.highlight_button.pack(side="left", padx=(0, 0))

        # 그룹 2: 정렬
        self.align_group = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.align_group.pack(side="left", padx=(0, 15))

        # 6. 정렬 버튼들
        self.align_left_button = ctk.CTkButton(
            self.align_group, text="⬅", width=30, height=30, fg_color=UI_COLORS["secondary"], command=self.align_left
        )
        self.align_left_button.pack(side="left", padx=(0, 5))

        self.align_center_button = ctk.CTkButton(
            self.align_group, text="⬛", width=30, height=30, fg_color=UI_COLORS["secondary"], command=self.align_center
        )
        self.align_center_button.pack(side="left", padx=(0, 5))

        self.align_right_button = ctk.CTkButton(
            self.align_group, text="➡", width=30, height=30, fg_color=UI_COLORS["secondary"], command=self.align_right
        )
        self.align_right_button.pack(side="left", padx=(0, 0))

        # 그룹 3: 편집 (실행취소/다시실행)
        self.edit_group = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.edit_group.pack(side="left", padx=(0, 15))

        # 7. 실행취소/다시실행 버튼
        self.undo_button = ctk.CTkButton(
            self.edit_group, text="↶", width=30, height=30, fg_color=UI_COLORS["secondary"], command=self.undo_action
        )
        self.undo_button.pack(side="left", padx=(0, 5))

        self.redo_button = ctk.CTkButton(
            self.edit_group, text="↷", width=30, height=30, fg_color=UI_COLORS["secondary"], command=self.redo_action
        )
        self.redo_button.pack(side="left", padx=(0, 0))

        # 그룹 4: 삽입 (링크, 그림판, 미디어, 이미지, 체크리스트)
        self.insert_group = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.insert_group.pack(side="left", padx=(0, 15))

        # 8. 삽입 버튼들
        self.link_button = ctk.CTkButton(
            self.insert_group, text="🔗", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_link
        )
        self.link_button.pack(side="left", padx=(0, 5))

        self.paint_button = ctk.CTkButton(
            self.insert_group, text="🖌️", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_paint
        )
        self.paint_button.pack(side="left", padx=(0, 5))

        self.media_button = ctk.CTkButton(
            self.insert_group, text="🎬", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_media
        )
        self.media_button.pack(side="left", padx=(0, 5))

        self.image_button = ctk.CTkButton(
            self.insert_group, text="🖼", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_image
        )
        self.image_button.pack(side="left", padx=(0, 5))

        self.checklist_button = ctk.CTkButton(
            self.insert_group, text="☑", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_checklist
        )
        self.checklist_button.pack(side="left", padx=(0, 5))

        self.table_button = ctk.CTkButton(
            self.insert_group, text="⊞", width=30, height=30, fg_color=UI_COLORS["insert"], command=self.insert_table
        )
        self.table_button.pack(side="left", padx=(0, 0))

        # 그룹 5: 내보내기
        self.export_group = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.export_group.pack(side="left", padx=(0, 0))

        self.export_button = ctk.CTkButton(
            self.export_group, text="📥", width=30, height=30, fg_color=UI_COLORS["primary"], command=self.export_memo
        )
        self.export_button.pack(side="left", padx=(0, 0))

        # === 텍스트 에디터와 줄 번호 영역 ===
        self.editor_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.editor_frame.grid(row=1, column=0, padx=20, pady=(0, 5), sticky="nsew")
        self.editor_frame.grid_rowconfigure(0, weight=1)
        self.editor_frame.grid_columnconfigure(1, weight=1)

        # 줄 번호 캔버스
        self.linenumbers = LineNumbers(self.editor_frame, width=50, bg="#2b2b2b", highlightthickness=0)
        self.linenumbers.grid(row=0, column=0, sticky="ns")

        self.textbox = ctk.CTkTextbox(
            self.editor_frame,
            font=("Roboto Medium", 16),
            undo=True,
            wrap="word",
            border_width=0,
            padx=5 # 텍스트와 줄 번호 사이 간격
        )
        self.textbox.grid(row=0, column=1, sticky="nsew")

        # 줄 번호 위젯에 텍스트 위젯 연결 및 스크롤 동기화
        self.linenumbers.attach(self.textbox._textbox)
        self.textbox._textbox.configure(yscrollcommand=self._on_text_scroll)

        # === 상태 표시줄 (글자 수/줄 수) ===
        self.status_frame = ctk.CTkFrame(self.main_frame, height=25, fg_color="transparent")
        self.status_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        
        self.status_label = ctk.CTkLabel(
            self.status_frame, 
            text="Lines: 1  Chars: 0", 
            font=("Roboto Medium", 12),
            text_color="gray"
        )
        self.status_label.pack(side="right")

        # ===== 중요: 단축키 바인딩을 먼저 해야 함! =====
        # KeyPress 핸들러보다 먼저 바인딩해야 우선순위가 높아짐
        # 해결책: textbox와 윈도우 양쪽에 바인딩 (한글 IME 우회)

        if self._platform == "darwin":
            # macOS: Command 키 바인딩
            # 클립보드 기본 기능은 Tkinter에서 자동 처리됨

            # 전체 선택 - Command+A
            self.bind_all("<Command-a>", lambda _: self.select_all())
            self.bind_all("<Mod1-a>", lambda _: self.select_all())

            # 실행취소/다시실행 - Command+Z, Command+Shift+Z
            self.bind_all("<Command-z>", lambda _: self.undo_action())
            self.bind_all("<Mod1-z>", lambda _: self.undo_action())
            self.bind_all("<Command-Shift-Z>", lambda _: self.redo_action())
            self.bind_all("<Shift-Mod1-z>", lambda _: self.redo_action())

            # 서식 - Command+B/I/U
            self.bind_all("<Command-b>", lambda _: self.toggle_bold())
            self.bind_all("<Mod1-b>", lambda _: self.toggle_bold())
            self.bind_all("<Command-i>", lambda _: self.toggle_italic())
            self.bind_all("<Mod1-i>", lambda _: self.toggle_italic())
            self.bind_all("<Command-u>", lambda _: self.toggle_underline())
            self.bind_all("<Mod1-u>", lambda _: self.toggle_underline())

            # 검색 - Command+F
            self.bind_all("<Command-f>", lambda _: self.show_find_dialog())
            self.bind_all("<Mod1-f>", lambda _: self.show_find_dialog())
        else:
            # Windows/Linux: Control 키
            self.bind_all("<Control-a>", lambda _: self.select_all())
            self.bind_all("<Control-z>", lambda _: self.undo_action())
            self.bind_all("<Control-y>", lambda _: self.redo_action())
            self.bind_all("<Control-b>", lambda _: self.toggle_bold())
            self.bind_all("<Control-i>", lambda _: self.toggle_italic())
            self.bind_all("<Control-u>", lambda _: self.toggle_underline())
            self.bind_all("<Control-f>", lambda _: self.show_find_dialog())

        # ===== 일반 이벤트 바인딩 (단축키 다음에) =====
        # 키보드 이벤트 바인딩 (자동 저장용 및 서식 적용)
        self.textbox._textbox.bind("<KeyRelease>", self.on_text_change)
        self.textbox._textbox.bind("<KeyPress>", self.on_key_press)

        # 클릭 이벤트 통합 핸들러 (링크, 체크박스, 이미지)
        self.textbox._textbox.bind("<Button-1>", self.handle_text_click)

        # 커서 위치 변경 시 현재 서식 상태 업데이트
        self.textbox._textbox.bind("<ButtonRelease-1>", self.update_current_format, add="+")
        self.textbox._textbox.bind("<Up>", self.update_current_format, add="+")
        self.textbox._textbox.bind("<Down>", self.update_current_format, add="+")
        self.textbox._textbox.bind("<Left>", self.update_current_format, add="+")
        self.textbox._textbox.bind("<Right>", self.update_current_format, add="+")

        # 초기 UI 렌더링
        self.refresh_sidebar()
        self.setup_tags() # 서식 태그 설정
        
        # 설정 로드 및 종료 이벤트 바인딩
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.create_new_memo() # 시작 시 새 메모 상태

    def _on_text_scroll(self, *args):
        """텍스트박스 스크롤 시 호출되는 콜백"""
        # CTkTextbox의 스크롤바를 업데이트하고, 줄번호 캔버스의 뷰를 이동
        self.textbox._y_scrollbar.set(*args)
        self.linenumbers.yview_moveto(args[0])
        self.linenumbers.redraw()

    def load_memos(self):
        """JSON 파일에서 메모 불러오기"""
        self.memos = self.data_manager.load_memos()

    def save_memos(self):
        """메모를 JSON 파일에 저장"""
        self.data_manager.save_memos(self.memos)

    def load_settings(self):
        """설정 파일에서 창 크기, 위치, 투명도, 항상 위 설정 불러오기"""
        settings = self.data_manager.load_settings()
        if settings:
            try:
                # 창 크기 및 위치 복원
                if "geometry" in settings:
                    self.geometry(settings["geometry"])
                
                # 투명도 복원
                if "opacity" in settings:
                    opacity = float(settings["opacity"])
                    self.attributes("-alpha", opacity)
                    self.opacity_slider.set(opacity)
                
                # 항상 위 설정 복원
                if "always_on_top" in settings:
                    self.always_on_top = settings["always_on_top"]
                    self.attributes("-topmost", self.always_on_top)
                    if self.always_on_top:
                        self.always_on_top_button.configure(fg_color=PASTEL_COLORS["primary"])
                    else:
                        self.always_on_top_button.configure(fg_color="transparent")
                        
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        """현재 설정을 파일에 저장"""
        settings = {
            "geometry": self.geometry(),
            "opacity": self.attributes("-alpha"),
            "always_on_top": self.always_on_top
        }
        self.data_manager.save_settings(settings)

    def cleanup_unused_files(self):
        """사용되지 않는 이미지 및 썸네일 파일 정리"""
        # 1. 현재 사용 중인 모든 파일 경로 수집
        used_files = set()
        for memo_data in self.memos.values():
            rich_content = memo_data.get("rich_content", [])
            if not rich_content:
                continue
            
            for segment in rich_content:
                if segment.get("type") == "image":
                    path = segment.get("path")
                    if path:
                        used_files.add(os.path.abspath(path))
                elif segment.get("type") == "media":
                    path = segment.get("thumbnail_path")
                    if path:
                        used_files.add(os.path.abspath(path))
                elif segment.get("type") == "paint":
                    path = segment.get("path")
                    if path:
                        used_files.add(os.path.abspath(path))

        # 2. 디렉토리 스캔 및 삭제
        dirs_to_clean = [
            get_resource_dir("memo_images"),
            get_resource_dir(os.path.join("memo_images", "thumbnails"))
        ]

        deleted_count = 0
        for dir_path in dirs_to_clean:
            if not os.path.exists(dir_path):
                continue
                
            for filename in os.listdir(dir_path):
                file_path = os.path.abspath(os.path.join(dir_path, filename))
                
                # 디렉토리는 건너뜀
                if os.path.isdir(file_path):
                    continue
                    
                # 사용되지 않는 파일이면 삭제
                if file_path not in used_files:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        logger.info(f"Deleted unused file: {filename}")
                    except OSError as e:
                        logger.error(f"Error deleting file {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} unused files.")

    def on_closing(self):
        """프로그램 종료 시 호출"""
        # 리소스 정리
        self._cleanup_resources()

        # 저장 타이머 정리
        if self.save_timer:
            self.after_cancel(self.save_timer)
            self.save_timer = None

        # 종료 전 미사용 파일 정리
        self.cleanup_unused_files()
        
        self.save_settings()
        self.destroy()

    def setup_tags(self):
        """텍스트 에디터의 서식 태그 설정"""
        # 기본 스타일 태그 (밑줄, 취소선은 폰트와 독립적)
        self.textbox._textbox.tag_config("underline", underline=True)
        self.textbox._textbox.tag_config("overstrike", overstrike=True)

        # 정렬 태그
        self.textbox._textbox.tag_config("align_left", justify="left")
        self.textbox._textbox.tag_config("align_center", justify="center")
        self.textbox._textbox.tag_config("align_right", justify="right")

    def _get_font_tag(self, family, size, weight, slant):
        """폰트 속성 조합에 해당하는 태그 이름을 반환하고, 필요시 설정"""
        tag = f"f|{family}|{size}|{weight}|{slant}"

        # 최적화: 이미 설정된 태그라면 재설정하지 않음
        if tag in self._configured_font_tags:
            return tag

        # 폰트 튜플 생성 (tkinter font style: "bold italic")
        style_parts = []
        if weight == "bold": style_parts.append("bold")
        if slant == "italic": style_parts.append("italic")
        style_str = " ".join(style_parts) if style_parts else ""

        # 항상 태그를 재설정하여 폰트가 정확하게 적용되도록 함
        self.textbox._textbox.tag_config(tag, font=(family, int(size), style_str))
        self._configured_font_tags.add(tag)
        return tag

    def _parse_font_tag(self, tag):
        """태그 이름에서 폰트 속성 추출"""
        if tag.startswith("f|"):
            parts = tag.split("|")
            if len(parts) == 5:
                return {"family": parts[1], "size": int(parts[2]), "weight": parts[3], "slant": parts[4]}
        return None

    def configure_tag_if_needed(self, tag_name):
        """동적 태그(색상, 폰트 등)가 설정되어 있는지 확인하고 적용"""
        # 색상 태그 처리 (예: color_#ff0000)
        if tag_name.startswith("color_"):
            color = tag_name.split("_")[1]
            self.textbox._textbox.tag_config(tag_name, foreground=color)

        # 하이라이트 태그 처리 (예: highlight_#ffff00)
        elif tag_name.startswith("highlight_"):
            color = tag_name.split("_")[1]
            self.textbox._textbox.tag_config(tag_name, background=color)

        # 링크 태그 처리 (예: link_https://example.com)
        elif tag_name.startswith("link_"):
            url = tag_name[5:]  # "link_" 제거
            self._setup_link_tag(tag_name, url)

        # 새로운 폰트 태그 처리 (f|Family|Size|Weight|Slant)
        elif tag_name.startswith("f|"):
            parts = tag_name.split("|")
            if len(parts) == 5:
                self._get_font_tag(parts[1], parts[2], parts[3], parts[4])

    def update_current_format(self, event=None):
        """커서 위치의 서식을 현재 입력 서식으로 설정"""
        # 수동 서식 모드인 경우 커서 이동으로 서식을 변경하지 않음
        if self.manual_format_mode:
            return

        try:
            # 현재 커서 위치의 태그 가져오기
            cursor_pos = self.textbox._textbox.index("insert")
            tags = self.textbox._textbox.tag_names(cursor_pos)
            self.current_input_tags = set(t for t in tags if t != "sel")
        except tkinter.TclError:
            # 텍스트 위젯이 아직 초기화되지 않았거나 잘못된 인덱스
            pass

        # 서식 버튼 상태 업데이트
        self.update_format_buttons()

    def on_key_press(self, event):
        """키 입력을 가로채서 서식과 함께 삽입"""
        # 단축키 (Command/Control 조합)는 통과시킴
        # macOS: state & 0x8 (Command), Windows/Linux: state & 0x4 (Control)
        is_shortcut = (event.state & 0x8) or (event.state & 0x4)  # Command 또는 Control 키

        # 한글 IME 우회: keycode로 단축키 직접 처리 (keysym이 ??로 나올 때)
        if is_shortcut and event.keysym == "??":
            # macOS keycode 매핑 (실제 측정값)
            keycode_map = {
                # 서식
                184549474: 'b',  # Bold
                570425449: 'i',  # Italic
                536871029: 'u',  # Underline
                # 편집
                97: 'a',         # Select All (한글 모드에서 keycode가 작음)
                134217827: 'c',  # Copy
                150995062: 'v',  # Paste
                117440632: 'x',  # Cut
                100663418: 'z',  # Undo
                # 기타
                50331750: 'f',   # Find
            }

            key = keycode_map.get(event.keycode)
            if key:
                logger.debug(f"Korean IME shortcut detected: keycode={event.keycode} -> {key}")

                # 직접 함수 호출
                if key == 'b':
                    self.toggle_bold()
                    return "break"
                elif key == 'i':
                    self.toggle_italic()
                    return "break"
                elif key == 'u':
                    self.toggle_underline()
                    return "break"
                elif key == 'f':
                    self.show_find_dialog()
                    return "break"
                elif key == 'a':
                    self.select_all()
                    return "break"
                elif key == 'c':
                    self.copy_text()
                    return "break"
                elif key == 'v':
                    self.paste_text()
                    return "break"
                elif key == 'x':
                    self.cut_text()
                    return "break"
                elif key == 'z':
                    if event.state & 0x1:  # Shift 키
                        self.redo_action()
                    else:
                        self.undo_action()
                    return "break"

        # 단축키는 다른 핸들러가 처리하도록 통과
        if is_shortcut:
            logger.debug(f"Shortcut detected: keysym={event.keysym}, keycode={event.keycode}, state=0x{event.state:x}")
            return

        # 특수 키는 무시 (Backspace, Delete, 방향키 등)
        if len(event.char) == 0 or event.char in ['\x08', '\x7f']:
            return

        # Space, Enter, Tab을 입력하면 수동 서식 모드 해제 (단어/문단 구분)
        if event.char in [' ', '\n', '\r', '\t']:
            if self.manual_format_mode:
                # 현재 문자에 서식을 적용한 후 모드 해제
                def reset_mode():
                    self.manual_format_mode = False
                    self.update_format_buttons()
                self.textbox.after(50, reset_mode)

        # 서식 태그가 있으면 기본 입력을 막고 직접 삽입
        if self.current_input_tags:
            # 현재 커서 위치에 문자를 태그와 함께 삽입
            self.textbox._textbox.insert("insert", event.char, tuple(self.current_input_tags))
            # 기본 키 입력 동작을 막기 위해 "break" 반환
            return "break"


    def _update_input_font_attribute(self, attr, value=None):
        """현재 입력 서식의 폰트 속성 업데이트 (선택 영역이 없을 때)"""
        # 현재 입력 태그에서 폰트 정보 추출
        font_info = {"family": "Roboto Medium", "size": 16, "weight": "normal", "slant": "roman"}
        old_font_tag = None

        for tag in self.current_input_tags:
            parsed = self._parse_font_tag(tag)
            if parsed:
                font_info = parsed
                old_font_tag = tag
                break

        # 토글 동작을 위한 타겟 값 결정
        target_value = value
        if attr in ["weight", "slant"] and value is None:
            if attr == "weight":
                target_value = "normal" if font_info["weight"] == "bold" else "bold"
            elif attr == "slant":
                target_value = "roman" if font_info["slant"] == "italic" else "italic"

        # 속성 변경
        if attr == "weight":
            font_info["weight"] = target_value
        elif attr == "slant":
            font_info["slant"] = target_value
        elif attr == "family":
            font_info["family"] = value
        elif attr == "size":
            font_info["size"] = int(value)

        # 새 폰트 태그 생성
        new_font_tag = self._get_font_tag(
            font_info["family"],
            font_info["size"],
            font_info["weight"],
            font_info["slant"]
        )

        # 기존 폰트 태그 제거하고 새 태그 추가
        if old_font_tag:
            self.current_input_tags.discard(old_font_tag)
        self.current_input_tags.add(new_font_tag)

        # 수동 서식 모드 활성화
        self.manual_format_mode = True

    def apply_tag_to_selection(self, tag_name):
        """선택된 영역에 태그 적용 (토글 아님)"""
        try:
            self.configure_tag_if_needed(tag_name)
            self.textbox._textbox.tag_add(tag_name, "sel.first", "sel.last")
            self.on_text_change()
        except tkinter.TclError:
            # 선택 영역이 없는 경우, 현재 입력 서식에 추가
            if tag_name not in self.current_input_tags:
                self.current_input_tags.add(tag_name)

    def toggle_tag(self, tag_name):
        """선택된 영역의 태그 토글"""
        try:
            current_tags = self.textbox._textbox.tag_names("sel.first")
            self.configure_tag_if_needed(tag_name)
            if tag_name in current_tags:
                self.textbox._textbox.tag_remove(tag_name, "sel.first", "sel.last")
            else:
                self.textbox._textbox.tag_add(tag_name, "sel.first", "sel.last")
            self.on_text_change()
        except tkinter.TclError:
            # 선택 영역이 없는 경우, 현재 입력 서식을 토글
            if tag_name in self.current_input_tags:
                self.current_input_tags.discard(tag_name)
            else:
                self.configure_tag_if_needed(tag_name)
                self.current_input_tags.add(tag_name)
            # 수동 서식 모드 활성화
            self.manual_format_mode = True

    def apply_font_attribute(self, attr, value=None):
        """선택 영역의 폰트 속성(패밀리, 사이즈, 굵기, 기울임) 변경"""
        try:
            sel_start = self.textbox._textbox.index("sel.first")
            sel_end = self.textbox._textbox.index("sel.last")
        except tkinter.TclError:
            # 선택된 영역이 없으면 현재 입력 서식 업데이트
            self._update_input_font_attribute(attr, value)
            return

        # 구간별 서식 적용을 위한 내부 함수
        def process_segment(start, end, tags):
            # 현재 구간의 폰트 정보 파악
            font_info = {"family": "Roboto Medium", "size": 16, "weight": "normal", "slant": "roman"}
            old_font_tag = None
            
            for t in tags:
                parsed = self._parse_font_tag(t)
                if parsed:
                    font_info = parsed
                    old_font_tag = t
                    break
            
            # 속성 변경
            if attr == "weight": font_info["weight"] = target_value
            elif attr == "slant": font_info["slant"] = target_value
            elif attr == "family": font_info["family"] = value
            elif attr == "size": font_info["size"] = int(value)
            
            # 새 태그 생성 및 적용
            new_tag = self._get_font_tag(font_info["family"], font_info["size"], font_info["weight"], font_info["slant"])
            
            if old_font_tag and old_font_tag != new_tag:
                self.textbox._textbox.tag_remove(old_font_tag, start, end)
            if new_tag != old_font_tag:
                self.textbox._textbox.tag_add(new_tag, start, end)

        # 1. 토글 동작을 위한 타겟 값 결정 (Bold/Italic)
        target_value = value
        if attr in ["weight", "slant"] and value is None:
            # 첫 글자의 상태를 확인하여 반대로 토글
            first_tags = self.textbox._textbox.tag_names("sel.first")
            current_font = {"family": "Roboto Medium", "size": 16, "weight": "normal", "slant": "roman"}
            for tag in first_tags:
                parsed = self._parse_font_tag(tag)
                if parsed:
                    current_font = parsed
                    break
            
            if attr == "weight":
                target_value = "normal" if current_font["weight"] == "bold" else "bold"
            elif attr == "slant":
                target_value = "roman" if current_font["slant"] == "italic" else "italic"

        # 2. 선택 영역을 순회하며 각 구간별로 태그 업데이트
        # dump를 사용하여 태그가 변경되는 구간(segment)을 파악
        dump_data = self.textbox._textbox.dump(sel_start, sel_end, tag=True, text=True)
        
        current_index = sel_start
        current_tags = set(self.textbox._textbox.tag_names(sel_start))
        
        for key, val, index in dump_data:
            # 인덱스가 바뀌었으면 이전 구간 처리
            if self.textbox._textbox.compare(index, "!=", current_index):
                process_segment(current_index, index, current_tags)
                current_index = index

            # 태그 상태 업데이트
            if key == "tagon": current_tags.add(val)
            elif key == "tagoff": current_tags.discard(val)

        # 루프 종료 후 마지막 구간 처리 (이 부분이 누락되어 있었음)
        if self.textbox._textbox.compare(current_index, "<", sel_end):
            process_segment(current_index, sel_end, current_tags)

        self.on_text_change()

    def update_format_buttons(self):
        """현재 서식 상태에 따라 버튼 색상 업데이트"""
        # 폰트 태그를 한 번만 파싱 (성능 최적화)
        parsed_font_tags = [self._parse_font_tag(t) for t in self.current_input_tags]
        parsed_font_tags = [p for p in parsed_font_tags if p is not None]

        # Bold 버튼 상태
        has_bold = any(p.get("weight") == "bold" for p in parsed_font_tags)
        self.bold_button.configure(fg_color=PASTEL_COLORS["primary"] if has_bold else UI_COLORS["text_format"])

        # Italic 버튼 상태
        has_italic = any(p.get("slant") == "italic" for p in parsed_font_tags)
        self.italic_button.configure(fg_color=PASTEL_COLORS["primary"] if has_italic else UI_COLORS["text_format"])

        # Underline 버튼 상태
        has_underline = "underline" in self.current_input_tags
        self.underline_button.configure(fg_color=PASTEL_COLORS["primary"] if has_underline else UI_COLORS["text_format"])

        # Overstrike 버튼 상태
        has_overstrike = "overstrike" in self.current_input_tags
        self.strike_button.configure(fg_color=PASTEL_COLORS["primary"] if has_overstrike else UI_COLORS["text_format"])

    def toggle_bold(self):
        self.apply_font_attribute("weight")
        self.update_format_buttons()
        return "break"

    def toggle_italic(self):
        self.apply_font_attribute("slant")
        self.update_format_buttons()
        return "break"

    def toggle_underline(self):
        self.toggle_tag("underline")
        self.update_format_buttons()
        return "break"

    def toggle_overstrike(self):
        self.toggle_tag("overstrike")
        self.update_format_buttons()

    def change_color(self):
        color = colorchooser.askcolor(title="Choose Text Color")[1]
        if color:
            tag_name = f"color_{color}"
            self.apply_tag_to_selection(tag_name)

    def change_highlight(self):
        """텍스트 하이라이트 (배경색) 변경"""
        color = colorchooser.askcolor(title="Choose Highlight Color")[1]
        if color:
            tag_name = f"highlight_{color}"
            # 하이라이트 태그 설정
            self.textbox._textbox.tag_config(tag_name, background=color)
            self.apply_tag_to_selection(tag_name)

    def align_left(self):
        """왼쪽 정렬"""
        self.apply_alignment("align_left")

    def align_center(self):
        """가운데 정렬"""
        self.apply_alignment("align_center")

    def align_right(self):
        """오른쪽 정렬"""
        self.apply_alignment("align_right")

    def apply_alignment(self, align_tag):
        """정렬 태그 적용 (현재 줄 또는 선택된 줄들에)"""
        try:
            # 선택 영역이 있는 경우
            sel_start = self.textbox._textbox.index("sel.first linestart")
            sel_end = self.textbox._textbox.index("sel.last lineend")
        except tkinter.TclError:
            # 선택 영역이 없는 경우 현재 줄
            sel_start = self.textbox._textbox.index("insert linestart")
            sel_end = self.textbox._textbox.index("insert lineend")

        # 기존 정렬 태그 제거
        for tag in ["align_left", "align_center", "align_right"]:
            self.textbox._textbox.tag_remove(tag, sel_start, sel_end)

        # 새 정렬 태그 적용
        self.textbox._textbox.tag_add(align_tag, sel_start, sel_end)
        self.on_text_change()

    def undo_action(self):
        """실행 취소"""
        try:
            self.textbox._textbox.edit_undo()
        except tkinter.TclError:
            # 실행 취소할 작업이 없음
            pass

    def redo_action(self):
        """다시 실행"""
        try:
            self.textbox._textbox.edit_redo()
        except tkinter.TclError:
            # 다시 실행할 작업이 없음
            pass

    def select_all(self):
        """전체 선택"""
        self.textbox._textbox.tag_add("sel", "1.0", "end-1c")
        self.textbox._textbox.mark_set("insert", "end-1c")
        return "break"

    def copy_text(self):
        """선택한 텍스트 복사 (Tkinter 내장 함수 사용)"""
        try:
            # 선택 영역이 있는지 확인
            if not self.textbox._textbox.tag_ranges("sel"):
                return "break"

            # 선택 영역의 시작과 끝 인덱스
            sel_start = self.textbox._textbox.index("sel.first")
            sel_end = self.textbox._textbox.index("sel.last")

            # 선택 영역에 window(위젯)가 포함되어 있는지 확인
            has_widget = False
            for key, _, _ in self.textbox._textbox.dump(sel_start, sel_end, window=True):
                if key == "window":
                    has_widget = True
                    break

            if has_widget:
                # 위젯이 포함된 경우 경고 메시지
                import tkinter.messagebox as messagebox
                messagebox.showwarning(
                    "복사 제한",
                    "그림판이 포함된 영역은 복사할 수 없습니다.\n\n그림판을 복제하려면 더블클릭하여 편집 모드로 들어간 후\n'저장' 버튼으로 이미지 파일로 저장하세요."
                )
                return "break"

            # 일반 텍스트는 정상적으로 복사
            self.textbox._textbox.event_generate("<<Copy>>")
        except Exception as e:
            logger.error(f"Copy failed: {e}")
        return "break"

    def cut_text(self):
        """선택한 텍스트 잘라내기 (Tkinter 내장 함수 사용)"""
        try:
            # 선택 영역이 있는지 확인
            if not self.textbox._textbox.tag_ranges("sel"):
                return "break"

            # 선택 영역의 시작과 끝 인덱스
            sel_start = self.textbox._textbox.index("sel.first")
            sel_end = self.textbox._textbox.index("sel.last")

            # 선택 영역에 window(위젯)가 포함되어 있는지 확인
            has_widget = False
            for key, _, _ in self.textbox._textbox.dump(sel_start, sel_end, window=True):
                if key == "window":
                    has_widget = True
                    break

            if has_widget:
                # 위젯이 포함된 경우 경고 메시지
                import tkinter.messagebox as messagebox
                messagebox.showwarning(
                    "잘라내기 제한",
                    "그림판이 포함된 영역은 잘라낼 수 없습니다.\n\n그림판을 삭제하려면 선택한 후 Delete 키를 누르세요."
                )
                return "break"

            # 일반 텍스트는 정상적으로 잘라내기
            self.textbox._textbox.event_generate("<<Cut>>")
        except Exception as e:
            logger.error(f"Cut failed: {e}")
        return "break"

    def paste_text(self):
        """클립보드에서 텍스트 붙여넣기 (Tkinter 내장 함수 사용)"""
        try:
            self.textbox._textbox.event_generate("<<Paste>>")
        except Exception as e:
            logger.error(f"Paste failed: {e}")
        return "break"

    def show_find_dialog(self):
        """찾기/바꾸기 다이얼로그 표시"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("찾기 및 바꾸기")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()

        # 찾을 텍스트
        ctk.CTkLabel(dialog, text="찾을 내용:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        find_entry = ctk.CTkEntry(dialog, width=250)
        find_entry.grid(row=0, column=1, padx=10, pady=10)

        # 바꿀 텍스트
        ctk.CTkLabel(dialog, text="바꿀 내용:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        replace_entry = ctk.CTkEntry(dialog, width=250)
        replace_entry.grid(row=1, column=1, padx=10, pady=10)

        # 버튼들
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)

        ctk.CTkButton(
            button_frame, text="찾기", width=80,
            command=lambda: self.find_text(find_entry.get())
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame, text="바꾸기", width=80,
            command=lambda: self.replace_text(find_entry.get(), replace_entry.get())
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame, text="모두 바꾸기", width=100,
            command=lambda: self.replace_all_text(find_entry.get(), replace_entry.get())
        ).pack(side="left", padx=5)

        find_entry.focus()

    def find_text(self, search_text):
        """텍스트 찾기"""
        if not search_text:
            return

        # 이전 검색 결과 하이라이트 제거
        self.textbox._textbox.tag_remove("search", "1.0", "end")

        # 현재 커서 위치부터 검색
        start_pos = self.textbox._textbox.index("insert")
        pos = self.textbox._textbox.search(search_text, start_pos, "end")

        if pos:
            # 찾은 위치로 이동하고 하이라이트
            end_pos = f"{pos}+{len(search_text)}c"
            self.textbox._textbox.tag_add("search", pos, end_pos)
            self.textbox._textbox.tag_config("search", background="yellow", foreground="black")
            self.textbox._textbox.mark_set("insert", end_pos)
            self.textbox._textbox.see(pos)
        else:
            # 처음부터 다시 검색
            pos = self.textbox._textbox.search(search_text, "1.0", "end")
            if pos:
                end_pos = f"{pos}+{len(search_text)}c"
                self.textbox._textbox.tag_add("search", pos, end_pos)
                self.textbox._textbox.tag_config("search", background="yellow", foreground="black")
                self.textbox._textbox.mark_set("insert", end_pos)
                self.textbox._textbox.see(pos)

    def replace_text(self, search_text, replace_text):
        """현재 선택된 텍스트 바꾸기"""
        try:
            if self.textbox._textbox.get("sel.first", "sel.last") == search_text:
                self.textbox._textbox.delete("sel.first", "sel.last")
                self.textbox._textbox.insert("insert", replace_text)
                self.on_text_change()
        except tkinter.TclError:
            # 선택 영역이 없으면 찾기 실행
            self.find_text(search_text)

    def replace_all_text(self, search_text, replace_text):
        """모든 텍스트 바꾸기"""
        if not search_text:
            return

        count = 0
        pos = "1.0"
        while True:
            pos = self.textbox._textbox.search(search_text, pos, "end")
            if not pos:
                break
            end_pos = f"{pos}+{len(search_text)}c"
            self.textbox._textbox.delete(pos, end_pos)
            self.textbox._textbox.insert(pos, replace_text)
            pos = f"{pos}+{len(replace_text)}c"
            count += 1

        self.on_text_change()
        print(f"{count}개 항목을 바꿨습니다.")

    def insert_bullet(self):
        """글머리 기호 삽입"""
        # 현재 줄의 시작 부분에 글머리 기호 삽입
        current_line = self.textbox._textbox.index("insert linestart")
        self.textbox._textbox.insert(current_line, "• ")

    def _setup_link_tag(self, tag_name, url):
        """링크 태그 설정 (스타일만 설정, 클릭은 통합 핸들러에서 처리)"""
        self.textbox._textbox.tag_config(tag_name, foreground="blue", underline=True)
        # 마우스 커서 변경만 처리
        self.textbox._textbox.tag_bind(tag_name, "<Enter>", lambda _: self.textbox._textbox.config(cursor="hand2"))
        self.textbox._textbox.tag_bind(tag_name, "<Leave>", lambda _: self.textbox._textbox.config(cursor=""))

    def insert_link(self):
        """링크 삽입"""
        dialog = ctk.CTkInputDialog(text="URL을 입력하세요:", title="링크 삽입")
        url = dialog.get_input()

        if url:
            tag_name = f"link_{url}"
            self._setup_link_tag(tag_name, url)

            try:
                # 선택된 텍스트가 있으면 링크로 변환
                start = self.textbox._textbox.index("sel.first")
                end = self.textbox._textbox.index("sel.last")
                self.textbox._textbox.tag_add(tag_name, start, end)
                self.on_text_change()
            except tkinter.TclError:
                # 선택 영역이 없으면 URL 자체를 삽입
                self.textbox._textbox.insert("insert", url)
                start = f"insert-{len(url)}c"
                end = "insert"
                self.textbox._textbox.tag_add(tag_name, start, end)

    def open_url(self, url):
        """브라우저에서 URL 열기"""
        import webbrowser
        webbrowser.open(url)

    def on_search(self, event=None):
        """메모 검색"""
        search_text = self.search_entry.get().lower()
        if not search_text:
            self.search_mode = False
            self.refresh_sidebar()
            return

        self.search_mode = True
        # 검색 결과 필터링
        filtered_memos = {}
        for memo_id, data in self.memos.items():
            title = data.get("title", "").lower()
            content = data.get("content", "").lower()
            tags = data.get("tags", [])
            tags_str = " ".join(tags).lower()

            if search_text in title or search_text in content or search_text in tags_str:
                filtered_memos[memo_id] = data

        self.refresh_sidebar(filtered_memos)

    def add_tag(self, event=None):
        """현재 메모에 태그 추가"""
        if not self.current_memo_id:
            return

        tag = self.tag_entry.get().strip()
        if not tag:
            return

        if "tags" not in self.memos[self.current_memo_id]:
            self.memos[self.current_memo_id]["tags"] = []

        if tag not in self.memos[self.current_memo_id]["tags"]:
            self.memos[self.current_memo_id]["tags"].append(tag)
            self.save_memos()
            self.refresh_sidebar()

        self.tag_entry.delete(0, "end")

    def manage_tags(self):
        """태그 관리 다이얼로그"""
        if not self.current_memo_id:
            import tkinter.messagebox as messagebox
            messagebox.showinfo("알림", "먼저 메모를 선택하세요.")
            return

        tags = self.memos[self.current_memo_id].get("tags", [])
        if not tags:
            import tkinter.messagebox as messagebox
            messagebox.showinfo("알림", "이 메모에 태그가 없습니다.")
            return

        # 태그 관리 다이얼로그
        dialog = ctk.CTkToplevel(self)
        dialog.title("태그 관리")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        # 태그 리스트
        ctk.CTkLabel(dialog, text="현재 태그:", font=("Roboto Medium", 14, "bold")).pack(pady=(20, 10))

        tags_frame = ctk.CTkScrollableFrame(dialog, height=150)
        tags_frame.pack(fill="both", expand=True, padx=20, pady=10)

        def refresh_tag_list():
            for widget in tags_frame.winfo_children():
                widget.destroy()

            current_tags = self.memos[self.current_memo_id].get("tags", [])
            for tag in current_tags:
                tag_row = ctk.CTkFrame(tags_frame, fg_color="transparent")
                tag_row.pack(fill="x", pady=2)

                ctk.CTkLabel(tag_row, text=f"#{tag}", font=("Roboto Medium", 12)).pack(side="left", padx=5)

                # 삭제 버튼
                delete_btn = ctk.CTkButton(
                    tag_row,
                    text="❌",
                    width=30,
                    height=25,
                    fg_color=PASTEL_COLORS["danger"],
                    command=lambda t=tag: remove_tag(t)
                )
                delete_btn.pack(side="right")

        def remove_tag(tag):
            if "tags" in self.memos[self.current_memo_id]:
                if tag in self.memos[self.current_memo_id]["tags"]:
                    self.memos[self.current_memo_id]["tags"].remove(tag)
                    self.save_memos()
                    self.refresh_sidebar()
                    refresh_tag_list()

        refresh_tag_list()

        # 닫기 버튼
        ctk.CTkButton(dialog, text="닫기", command=dialog.destroy).pack(pady=10)

    def toggle_pin(self):
        """현재 메모 고정/해제"""
        if not self.current_memo_id:
            return

        current_pinned = self.memos[self.current_memo_id].get("pinned", False)
        self.memos[self.current_memo_id]["pinned"] = not current_pinned
        self.save_memos()
        self.refresh_sidebar()

    def toggle_pin_filter(self):
        """고정된 메모만 보기 필터 토글"""
        self.pin_filter_active = not self.pin_filter_active

        # 버튼 색상 업데이트
        if self.pin_filter_active:
            self.pin_filter_button.configure(fg_color="#FFB74D")  # 더 진한 색상으로 활성화 표시
        else:
            self.pin_filter_button.configure(fg_color=PASTEL_COLORS["accent"])

        self.refresh_sidebar()

    def toggle_lock(self):
        """현재 메모 잠금/해제"""
        if not self.current_memo_id:
            return

        is_locked = self.memos[self.current_memo_id].get("locked", False)

        if is_locked:
            # 잠금 해제: 비밀번호 확인
            password = self.memos[self.current_memo_id].get("password", "")
            password_hash = self.memos[self.current_memo_id].get("password_hash", "")
            dialog = ctk.CTkInputDialog(text="비밀번호를 입력하세요:", title="잠금 해제")
            input_password = dialog.get_input()

            # 해시값이 있으면 해시 비교, 없으면 평문 비교 (하위 호환성)
            password_match = False
            if password_hash:
                input_hash = hashlib.sha256(input_password.encode()).hexdigest()
                password_match = (input_hash == password_hash)
            else:
                password_match = (input_password == password)

            if password_match:
                self.memos[self.current_memo_id]["locked"] = False
                self.memos[self.current_memo_id]["password"] = ""
                self.memos[self.current_memo_id]["password_hash"] = ""
                self.save_memos()
                self.refresh_sidebar()
            else:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
        else:
            # 잠금 설정: 비밀번호 입력
            dialog = ctk.CTkInputDialog(text="설정할 비밀번호를 입력하세요:", title="잠금 설정")
            password = dialog.get_input()

            if password:
                self.memos[self.current_memo_id]["locked"] = True
                # 비밀번호를 해시하여 저장 (보안 강화)
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                self.memos[self.current_memo_id]["password_hash"] = password_hash
                # 하위 호환성을 위해 password 필드는 빈 문자열로 설정
                self.memos[self.current_memo_id]["password"] = ""
                self.save_memos()
                self.refresh_sidebar()

    def insert_paint(self):
        """그림판(PaintFrame) 삽입"""
        # 캔버스 크기 입력 받기
        dialog = ctk.CTkToplevel(self)
        dialog.title("캔버스 크기 설정")
        dialog.geometry("300x150")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="너비 (Width):").grid(row=0, column=0, padx=10, pady=10)
        width_entry = ctk.CTkEntry(dialog, width=100)
        width_entry.insert(0, "600")
        width_entry.grid(row=0, column=1, padx=10, pady=10)

        ctk.CTkLabel(dialog, text="높이 (Height):").grid(row=1, column=0, padx=10, pady=10)
        height_entry = ctk.CTkEntry(dialog, width=100)
        height_entry.insert(0, "400")
        height_entry.grid(row=1, column=1, padx=10, pady=10)

        def create_canvas():
            try:
                w = int(width_entry.get())
                h = int(height_entry.get())
                dialog.destroy()

                # 텍스트 위젯 내에 PaintFrame 생성 및 삽입
                # master를 textbox._textbox로 설정하여 스크롤 시 함께 이동하도록 함
                paint_frame = PaintFrame(self.textbox._textbox, width=w, height=h, use_overlay_toolbar=False)

                # 자동 저장 경로 설정 (memo_images 디렉토리에 고유 파일명으로 저장)
                paint_images_dir = get_resource_dir("memo_images")
                paint_filename = f"paint_{uuid.uuid4().hex}.pproj"
                paint_frame.auto_save_path = os.path.join(paint_images_dir, paint_filename)

                self.textbox._textbox.insert("insert", "\n")
                self.textbox._textbox.window_create("insert", window=paint_frame, padx=5, pady=5)
                self.textbox._textbox.insert("insert", "\n")

                # PaintFrame 객체가 가비지 컬렉션되지 않도록 참조 저장
                self.paint_frames.append(paint_frame)

                # 변경 사항 자동 저장 트리거
                self.on_text_change()

            except ValueError:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", "올바른 숫자를 입력하세요.")

        ctk.CTkButton(dialog, text="생성", command=create_canvas).grid(row=2, column=0, columnspan=2, pady=10)

    def insert_image(self):
        """이미지 삽입 및 렌더링 (파일 복사본 저장)"""
        from tkinter import filedialog
        import shutil

        try:
            from PIL import Image, ImageTk
        except ImportError:
            import tkinter.messagebox as messagebox
            messagebox.showerror("오류", "PIL/Pillow 라이브러리가 설치되어 있지 않습니다.\n\n터미널에서 다음 명령어를 실행하세요:\npip install Pillow")
            return

        file_path = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")]
        )

        if file_path:
            try:
                # 이미지 저장 디렉토리 생성 (안전한 경로 처리)
                images_dir = get_resource_dir("memo_images")

                # 고유한 파일명으로 이미지 복사
                file_ext = os.path.splitext(file_path)[1]
                new_filename = f"{uuid.uuid4().hex}{file_ext}"
                copied_path = os.path.join(images_dir, new_filename)

                try:
                    shutil.copy2(file_path, copied_path)
                except (IOError, OSError) as e:
                    logger.error(f"Failed to copy image file: {e}")
                    import tkinter.messagebox as messagebox
                    messagebox.showerror("오류", "이미지 파일을 복사할 수 없습니다. 디스크 공간이나 권한을 확인하세요.")
                    return

                # 이미지 로드 및 리사이즈
                img = Image.open(copied_path)
                original_width, original_height = img.width, img.height

                # 최대 너비를 텍스트 박스 너비의 80%로 제한
                max_width = 600
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_size = (max_width, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                # PhotoImage로 변환
                photo = ImageTk.PhotoImage(img)

                # 이미지를 텍스트 위젯에 삽입
                current_index = self.textbox._textbox.index("insert")
                self.textbox._textbox.insert(current_index, "\n")
                image_index = self.textbox._textbox.index("insert")
                self.textbox._textbox.image_create(image_index, image=photo, name=new_filename)
                self.textbox._textbox.insert("insert", "\n")

                # 이미지 태그 생성 및 적용
                image_tag = f"img_{new_filename}"
                self.textbox._textbox.tag_add(image_tag, image_index)

                # 이미지 객체 및 메타데이터 참조 유지
                if not hasattr(self, 'images'):
                    self.images = {}
                self.images[image_tag] = {
                    'photo': photo,
                    'path': copied_path,
                    'original_width': original_width,
                    'original_height': original_height,
                    'display_width': img.width,
                    'display_height': img.height,
                    'index': image_index
                }

                # 이미지 더블클릭 이벤트 바인딩 (크기 조절용)
                self.textbox._textbox.tag_bind(image_tag, "<Double-Button-1>",
                    lambda _, tag=image_tag: self.resize_image_dialog(tag))

                self.on_text_change()
                logger.info(f"Image inserted: {new_filename}")
            except Exception as e:
                logger.error(f"Failed to insert image: {e}", exc_info=True)
                import tkinter.messagebox as messagebox
                error_msg = "이미지를 불러올 수 없습니다."
                if isinstance(e, IOError):
                    error_msg = "이미지 파일을 읽을 수 없습니다. 파일이 손상되었거나 형식이 지원되지 않을 수 있습니다."
                elif isinstance(e, MemoryError):
                    error_msg = "이미지가 너무 커서 메모리 부족이 발생했습니다. 더 작은 이미지를 사용하세요."
                messagebox.showerror("이미지 삽입 실패", error_msg)

    def insert_media(self):
        """미디어 링크 삽입 (YouTube, 치지직, Twitch)"""
        # 커스텀 다이얼로그 생성 (한글 모드 단축키 지원)
        url = dialogs.show_custom_input_dialog(
            self,
            "미디어 삽입",
            "미디어 URL을 입력하세요:\n(YouTube, 치지직, Twitch)"
        )

        if not url:
            return

        # 미디어 타입 감지
        media_info = media_utils.parse_media_url(url)

        if not media_info:
            # 일반 링크로 처리
            import tkinter.messagebox as messagebox
            result = messagebox.askyesno("확인", "지원되지 않는 미디어 URL입니다.\n일반 링크로 삽입하시겠습니까?")
            if result:
                self.insert_link()
            return

        # 썸네일 가져오기 및 미디어 위젯 생성
        self.insert_media_widget(media_info)

    def insert_media_widget(self, media_info):
        """미디어 위젯 생성 및 삽입"""
        try:
            from PIL import Image, ImageTk, ImageDraw, ImageFont
            import requests
            from io import BytesIO
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # 썸네일 다운로드
            thumbnail_url = media_utils.get_thumbnail_url(media_info)
            img = None

            if thumbnail_url:
                try:
                    logger.debug(f"Downloading thumbnail from: {thumbnail_url}")
                    # 이미지 다운로드 시에도 헤더 추가 (치지직 서버 차단 방지)
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                        'Referer': 'https://chzzk.naver.com/'
                    }
                    response = requests.get(thumbnail_url, headers=headers, timeout=10, verify=False)
                    img = Image.open(BytesIO(response.content))
                except Exception as e:
                    logger.debug(f"Thumbnail download failed: {e}")

            # 썸네일 실패 시 기본 이미지 생성 (검은 배경에 플랫폼 로고/텍스트)
            if img is None:
                logger.debug("Generating placeholder image")
                width, height = 480, 270
                img = Image.new('RGB', (width, height), color='#2C2C2C')
                draw = ImageDraw.Draw(img)
                
                # 플랫폼 이름 표시
                platform_name = media_info['platform'].upper()
                
                # 폰트 설정 (시스템 폰트 시도)
                font = ImageFont.load_default()
                try:
                    # macOS 기본 폰트 시도
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
                except:
                    pass
                
                # 텍스트 중앙 정렬
                try:
                    bbox = draw.textbbox((0, 0), platform_name, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                except:
                    text_w, text_h = draw.textsize(platform_name, font=font)
                
                draw.text(((width - text_w) / 2, (height - text_h) / 2), platform_name, fill='white', font=font)

            # 크기 조절 (16:9 비율 유지)
            max_width = 480
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            # 재생 버튼 오버레이 추가
            img = img.convert('RGBA')
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            center = (img.width // 2, img.height // 2)

            # 반투명 원형 배경
            draw.ellipse([center[0]-40, center[1]-40, center[0]+40, center[1]+40],
                        fill=(0, 0, 0, 128))

            # 재생 버튼 삼각형
            triangle = [
                (center[0]-15, center[1]-20),
                (center[0]-15, center[1]+20),
                (center[0]+20, center[1])
            ]
            draw.polygon(triangle, fill=(255, 255, 255, 255))

            img = Image.alpha_composite(img, overlay)

            # 플랫폼 라벨 추가
            platform_label = {
                'youtube': '🎬 YouTube',
                'chzzk': '🎮 치지직',
                'twitch': '💜 Twitch'
            }.get(media_info['platform'], '🎬 Media')

            # 메타데이터 가져오기 (media_utils 사용)
            metadata = media_utils.get_media_metadata(media_info)
            parts = [p for p in [metadata['channel'], metadata['title'], metadata['duration']] if p]
            if parts:
                platform_label = " - ".join(parts)

            # 라벨 배경
            label_height = 25
            label_bg = Image.new('RGBA', (img.width, label_height), (0, 0, 0, 180))
            img_with_label = Image.new('RGBA', (img.width, img.height + label_height), (0, 0, 0, 0))
            img_with_label.paste(img, (0, 0))
            img_with_label.paste(label_bg, (0, img.height), label_bg)

            # PhotoImage로 변환
            photo = ImageTk.PhotoImage(img_with_label)

            # 썸네일 캐시 저장 (안전한 경로 처리)
            thumbnails_dir = get_resource_dir(os.path.join("memo_images", "thumbnails"))

            cache_filename = f"{uuid.uuid4().hex}.png"
            cache_path = os.path.join(thumbnails_dir, cache_filename)

            try:
                img_with_label.save(cache_path, 'PNG')
            except (IOError, OSError) as e:
                logger.error(f"Failed to save media thumbnail: {e}")
                # 캐시 저장 실패해도 계속 진행 (미디어는 삽입됨)

            # 텍스트 위젯에 삽입
            current_index = self.textbox._textbox.index("insert")
            self.textbox._textbox.insert(current_index, "\n")
            image_index = self.textbox._textbox.index("insert")

            media_id = f"media_{uuid.uuid4().hex[:8]}"
            self.textbox._textbox.image_create(image_index, image=photo, name=media_id)
            self.textbox._textbox.insert("insert", "\n")
            self.textbox._textbox.insert("insert", f"{platform_label}\n")

            # 미디어 태그 생성
            media_tag = f"media_{media_id}"
            self.textbox._textbox.tag_add(media_tag, image_index)

            # 클릭 이벤트 - 더블클릭과 싱글클릭 구분
            # 더블클릭 우선 처리
            self.textbox._textbox.tag_bind(media_tag, "<Double-Button-1>",
                lambda e, tag=media_tag: self.on_media_double_click(e, tag))

            self.textbox._textbox.tag_bind(media_tag, "<Button-1>",
                lambda e, m=media_info: self.on_media_single_click(e, m))

            # 마우스 커서 변경
            self.textbox._textbox.tag_bind(media_tag, "<Enter>",
                lambda _: self.textbox._textbox.config(cursor="hand2"))
            self.textbox._textbox.tag_bind(media_tag, "<Leave>",
                lambda _: self.textbox._textbox.config(cursor=""))

            # 메타데이터 저장
            if not hasattr(self, 'medias'):
                self.medias = {}

            self.medias[media_tag] = {
                'photo': photo,
                'platform': media_info['platform'],
                'url': media_info['url'],
                'thumbnail_path': cache_path,
                'display_width': img_with_label.width,
                'display_height': img_with_label.height
            }

            self.on_text_change()
            logger.info(f"Media inserted: {media_info['platform']} - {media_info['url']}")

        except Exception as e:
            logger.error(f"Failed to insert media: {e}", exc_info=True)
            import tkinter.messagebox as messagebox
            error_msg = "미디어를 불러올 수 없습니다."
            if "requests" in str(type(e).__module__):
                error_msg = "미디어 썸네일을 다운로드할 수 없습니다. 인터넷 연결을 확인하세요."
            elif isinstance(e, IOError):
                error_msg = "미디어 파일을 저장할 수 없습니다. 디스크 공간이나 권한을 확인하세요."
            messagebox.showerror("미디어 삽입 실패", error_msg)

    def resize_image_dialog(self, image_tag):
        """이미지 크기 조절 다이얼로그"""
        if image_tag not in self.images:
            return

        image_data = self.images[image_tag]

        # 크기 입력 다이얼로그
        dialog = ctk.CTkToplevel(self)
        dialog.title("이미지 크기 조절")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()

        # 현재 크기 표시
        ctk.CTkLabel(dialog, text="현재 크기:", font=("Roboto Medium", 14, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(dialog, text=f"{image_data['display_width']} x {image_data['display_height']} px").pack(pady=(0, 10))

        # 원본 크기 표시
        ctk.CTkLabel(dialog, text="원본 크기:", font=("Roboto Medium", 12)).pack(pady=(0, 5))
        ctk.CTkLabel(dialog, text=f"{image_data['original_width']} x {image_data['original_height']} px").pack(pady=(0, 20))

        # 새 크기 입력
        input_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        input_frame.pack(pady=10)

        ctk.CTkLabel(input_frame, text="너비:").grid(row=0, column=0, padx=5, pady=5)
        width_entry = ctk.CTkEntry(input_frame, width=100)
        width_entry.insert(0, str(image_data['display_width']))
        width_entry.grid(row=0, column=1, padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="높이:").grid(row=1, column=0, padx=5, pady=5)
        height_entry = ctk.CTkEntry(input_frame, width=100)
        height_entry.insert(0, str(image_data['display_height']))
        height_entry.grid(row=1, column=1, padx=5, pady=5)

        # 비율 유지 체크박스
        keep_ratio_var = ctk.BooleanVar(value=True)
        ratio_checkbox = ctk.CTkCheckBox(dialog, text="비율 유지", variable=keep_ratio_var)
        ratio_checkbox.pack(pady=10)

        def apply_resize():
            try:
                new_width = int(width_entry.get())
                new_height = int(height_entry.get())

                if new_width <= 0 or new_height <= 0:
                    raise ValueError("크기는 양수여야 합니다")

                # 이미지 리사이즈 및 재삽입
                self.resize_image(image_tag, new_width, new_height)
                dialog.destroy()
            except ValueError as e:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", f"올바른 크기를 입력하세요: {str(e)}")

        # 비율 유지 기능
        def on_width_change(*args):
            if keep_ratio_var.get():
                try:
                    new_width = int(width_entry.get())
                    ratio = new_width / image_data['display_width']
                    new_height = int(image_data['display_height'] * ratio)
                    height_entry.delete(0, "end")
                    height_entry.insert(0, str(new_height))
                except:
                    pass

        width_entry.bind("<KeyRelease>", on_width_change)

        # 버튼들
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=20)

        ctk.CTkButton(button_frame, text="적용", width=80, command=apply_resize).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="취소", width=80, command=dialog.destroy).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="원본 크기", width=100,
            command=lambda: (width_entry.delete(0, "end"), width_entry.insert(0, str(image_data['original_width'])),
                           height_entry.delete(0, "end"), height_entry.insert(0, str(image_data['original_height'])))
        ).pack(side="left", padx=5)

    def resize_image(self, image_tag, new_width, new_height):
        """이미지 크기 변경 및 재렌더링"""
        if image_tag not in self.images:
            return

        try:
            from PIL import Image, ImageTk

            image_data = self.images[image_tag]

            # 원본 이미지 로드 및 리사이즈
            img = Image.open(image_data['path'])
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            # 기존 이미지 위치 찾기
            image_name = image_tag.split("img_")[1]

            # 텍스트 위젯에서 이미지 재생성
            # image_names()로 이미지 찾기
            for img_name in self.textbox._textbox.image_names():
                if img_name == image_name:
                    # 이미지 삭제 및 재삽입
                    # 이미지의 인덱스 찾기
                    ranges = self.textbox._textbox.tag_ranges(image_tag)
                    if ranges:
                        img_index = str(ranges[0])
                        self.textbox._textbox.delete(img_index)
                        self.textbox._textbox.image_create(img_index, image=photo, name=image_name)

                        # 메타데이터 업데이트
                        image_data['photo'] = photo
                        image_data['display_width'] = new_width
                        image_data['display_height'] = new_height

                        self.on_text_change()
                        break

        except Exception as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("오류", f"이미지 크기를 변경할 수 없습니다: {str(e)}")

    def insert_checklist(self):
        """체크리스트 항목 삽입"""
        current_line = self.textbox._textbox.index("insert linestart")
        self.textbox._textbox.insert(current_line, "☐ ")
        self.on_text_change()

    def insert_table(self):
        """표 삽입"""
        # 행/열 입력 다이얼로그
        dialog = ctk.CTkInputDialog(
            text="행 x 열 (예: 3x4):",
            title="표 만들기"
        )
        result = dialog.get_input()

        if not result:
            return

        try:
            # 입력 파싱 (3x4 형식)
            parts = result.lower().replace(" ", "").split("x")
            if len(parts) != 2:
                raise ValueError("잘못된 형식")

            rows = int(parts[0])
            cols = int(parts[1])

            if rows < 1 or cols < 1 or rows > 20 or cols > 20:
                raise ValueError("행과 열은 1-20 사이여야 합니다")

            # 표 위젯 생성
            table_widget = TableWidget(self.textbox._textbox, rows=rows, cols=cols)

            # 텍스트박스에 삽입
            self.textbox._textbox.window_create("insert", window=table_widget, padx=5, pady=5)
            self.table_widgets.append(table_widget)
            self.on_text_change()

        except ValueError as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("오류", f"올바른 형식으로 입력하세요 (예: 3x4)\n{str(e)}")

    def handle_text_click(self, event):
        """텍스트 클릭 통합 핸들러 - 링크, 체크박스, 이미지 처리"""
        try:
            # 클릭 위치의 인덱스 및 문자 확인
            index = self.textbox._textbox.index(f"@{event.x},{event.y}")
            char = self.textbox._textbox.get(index)

            # 1. 체크박스 토글
            if char == "☐":
                self.textbox._textbox.delete(index)
                self.textbox._textbox.insert(index, "☑")
                self.on_text_change()
                return "break"
            elif char == "☑":
                self.textbox._textbox.delete(index)
                self.textbox._textbox.insert(index, "☐")
                self.on_text_change()
                return "break"

            # 2. 링크 클릭 - 클릭 위치의 태그 확인
            tags = self.textbox._textbox.tag_names(index)
            for tag in tags:
                if tag.startswith("link_"):
                    url = tag[5:]  # "link_" 제거
                    logger.info(f"Link clicked: {url}")
                    try:
                        import webbrowser
                        webbrowser.open(url)
                    except Exception as e:
                        logger.error(f"Error opening browser: {e}")
                        import tkinter.messagebox as messagebox
                        messagebox.showerror("링크 열기 실패", "브라우저를 열 수 없습니다. 기본 브라우저 설정을 확인하세요.")
                    return "break"

            # 3. 이미지 클릭 (향후 확장용)
            # 이미지 더블클릭은 별도 바인딩 처리

        except Exception as e:
            logger.debug(f"Click handler error: {e}")

        # 기본 동작 허용
        return None

    def export_memo(self):
        """현재 메모 내보내기"""
        if not self.current_memo_id:
            return

        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("HTML files", "*.html"),
                ("Markdown files", "*.md"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            content = self.textbox.get("1.0", "end-1c")
            title = self.memos[self.current_memo_id].get("title", "Untitled")

            exporter.export_file(file_path, title, content)

            import tkinter.messagebox as messagebox
            messagebox.showinfo("완료", f"메모가 저장되었습니다: {file_path}")

    def toggle_format_painter(self):
        """서식 복사/붙여넣기 모드 토글"""
        if not self.format_painter_mode:
            # 서식 복사 모드 시작
            try:
                # 선택 영역의 태그 가져오기
                tags = self.textbox._textbox.tag_names("sel.first")
                self.copied_format = set(t for t in tags if t != "sel" and not t.startswith("link_"))
                self.format_painter_mode = True
                self.format_painter_button.configure(fg_color=UI_COLORS["success"])  # 활성화 표시
                # 마우스 클릭 이벤트 바인딩
                self.textbox._textbox.bind("<Button-1>", self.apply_copied_format, add="+")
            except tkinter.TclError:
                # 선택 영역이 없음
                pass
        else:
            # 서식 복사 모드 종료
            self.format_painter_mode = False
            self.format_painter_button.configure(fg_color=UI_COLORS["secondary"])
            # 이벤트 바인딩 해제는 update_current_format이 이미 바인딩되어 있으므로 생략

    def apply_copied_format(self, _=None):
        """복사한 서식을 선택 영역에 적용"""
        if not self.format_painter_mode or not self.copied_format:
            return

        # 약간 지연 후 적용 (선택 영역이 확정된 후)
        self.after(10, self._apply_format_delayed)

    def _apply_format_delayed(self):
        """지연 후 서식 적용"""
        try:
            start = self.textbox._textbox.index("sel.first")
            end = self.textbox._textbox.index("sel.last")

            # 복사한 태그들 적용
            for tag in self.copied_format:
                self.configure_tag_if_needed(tag)
                self.textbox._textbox.tag_add(tag, start, end)

            self.on_text_change()
        except tkinter.TclError:
            # 선택 영역이 없음
            pass
        finally:
            # 서식 복사 모드 종료
            self.format_painter_mode = False
            self.format_painter_button.configure(fg_color=UI_COLORS["secondary"])

    def change_font_family(self, family):
        self.apply_font_attribute("family", family)

    def change_font_size(self, size):
        self.apply_font_attribute("size", size)

    def change_opacity(self, value):
        """창 투명도 조절"""
        self.attributes("-alpha", value)

    def toggle_always_on_top(self):
        """창을 항상 위에 고정 토글"""
        self.always_on_top = not self.always_on_top
        self.attributes("-topmost", self.always_on_top)

        if self.always_on_top:
            self.always_on_top_button.configure(fg_color=PASTEL_COLORS["primary"])
        else:
            self.always_on_top_button.configure(fg_color="transparent")

    def update_status_bar(self):
        """글자 수 및 줄 수 업데이트"""
        try:
            content = self.textbox.get("1.0", "end-1c")
            char_count = len(content)
            # 논리적 줄 수 계산 (마지막 줄바꿈 문자 제외 위치 기준)
            line_count = int(self.textbox._textbox.index("end-1c").split('.')[0])
            self.status_label.configure(text=f"Lines: {line_count}  Chars: {char_count}")
        except Exception:
            pass

    def get_serialized_content(self, use_cache=True):
        """텍스트와 태그 정보를 포함하여 직렬화 (이미지, 미디어, PaintFrame 정보 포함)"""
        # 캐싱: 텍스트가 변경되지 않았으면 캐시 사용
        if use_cache and self._content_cache is not None:
            current_text = self.textbox.get("1.0", "end-1c")
            if self._content_cache.get('text') == current_text:
                return self._content_cache['data']

        content = []
        current_tags = set()
        # dump: 텍스트 위젯의 내용을 (key, value, index) 튜플 리스트로 반환
        dump_data = self.textbox._textbox.dump("1.0", "end-1c", text=True, tag=True, image=True, window=True)

        for key, value, index in dump_data:
            if key == "tagon" and value != "sel":
                current_tags.add(value)
            elif key == "tagoff" and value != "sel":
                current_tags.discard(value)
            elif key == "text":
                content.append({"text": value, "tags": list(current_tags)})
            elif key == "window":
                # PaintFrame 및 TableWidget 위젯 확인 및 저장
                try:
                    widget = self.textbox._textbox.nametowidget(value)
                    if isinstance(widget, PaintFrame):
                        # PaintFrame의 프로젝트 파일 경로 저장
                        if hasattr(widget, 'auto_save_path') and widget.auto_save_path:
                            content.append({
                                "type": "paint",
                                "path": widget.auto_save_path,
                                "width": widget.canvas_width,
                                "height": widget.canvas_height
                            })
                    elif isinstance(widget, TableWidget):
                        # TableWidget 데이터 저장
                        table_data = widget.get_table_data()
                        content.append({
                            "type": "table",
                            "data": table_data
                        })
                except Exception as e:
                    logger.error(f"Error processing widget: {e}")
            elif key == "image":
                # 이미지/미디어 정보 저장
                image_name = value

                # 미디어 태그 확인
                media_tag = f"media_{image_name}"
                if hasattr(self, 'medias') and media_tag in self.medias:
                    media_data = self.medias[media_tag]
                    content.append({
                        "type": "media",
                        "platform": media_data['platform'],
                        "url": media_data['url'],
                        "thumbnail_path": media_data['thumbnail_path'],
                        "display_width": media_data['display_width'],
                        "display_height": media_data['display_height']
                    })
                    continue

                # 이미지 태그 확인
                image_tag = f"img_{image_name}"
                if hasattr(self, 'images') and image_tag in self.images:
                    img_data = self.images[image_tag]
                    content.append({
                        "type": "image",
                        "path": img_data['path'],
                        "display_width": img_data['display_width'],
                        "display_height": img_data['display_height']
                    })

        # 캐시 업데이트
        if use_cache:
            current_text = self.textbox.get("1.0", "end-1c")
            self._content_cache = {'text': current_text, 'data': content}

        return content

    def _cleanup_resources(self):
        """메모리 누수 방지를 위한 리소스 정리"""
        # 미디어 클릭 타이머 정리
        if hasattr(self, '_media_click_timer'):
            for timer_id in list(self._media_click_timer.values()):
                try:
                    self.after_cancel(timer_id)
                except:
                    pass
            self._media_click_timer.clear()

        # 이미지 참조 정리
        if hasattr(self, 'images'):
            self.images.clear()

        # 미디어 참조 정리
        if hasattr(self, 'medias'):
            self.medias.clear()

        # 그림판 객체 참조 정리
        if hasattr(self, 'paint_frames'):
            self.paint_frames.clear()

        # 표 객체 참조 정리
        if hasattr(self, 'table_widgets'):
            self.table_widgets.clear()

    def create_new_memo(self):
        """화면을 비우고 새 메모 모드로 전환"""
        # 이전 메모 버튼을 파스텔 녹색으로 변경
        if self.current_memo_id and self.current_memo_id in self.memo_buttons:
            self.memo_buttons[self.current_memo_id].configure(fg_color="#C8E6C9")

        # 리소스 정리
        self._cleanup_resources()

        self.current_memo_id = None
        self.is_modified = False  # 새 메모는 수정되지 않은 상태
        self.textbox.delete("1.0", "end")
        self.current_input_tags = set()  # 서식 초기화
        self.manual_format_mode = False  # 수동 서식 모드 해제

        # 이미지/미디어 참조 초기화
        if not hasattr(self, 'images'):
            self.images = {}
        if not hasattr(self, 'medias'):
            self.medias = {}
        if not hasattr(self, 'paint_frames'):
            self.paint_frames = []
        if not hasattr(self, 'table_widgets'):
            self.table_widgets = []

        self.textbox.focus()
        self.update_status_bar()

    def rename_memo(self, memo_id):
        """메모 제목 변경 (더블 클릭 시)"""
        if memo_id in self.memos:
            current_title = self.memos[memo_id].get("title", "")
            dialog = ctk.CTkInputDialog(text="Enter new title:", title="Rename Memo")
            new_title = dialog.get_input()

            if new_title:
                self.memos[memo_id]["title"] = new_title
                # 수동 제목 설정 플래그 추가
                self.memos[memo_id]["custom_title"] = True
                self.save_memos()
                self.refresh_sidebar()

    def delete_memo(self):
        """현재 메모 삭제"""
        if self.current_memo_id is not None and self.current_memo_id in self.memos:
            # 저장 타이머가 있다면 취소 (삭제된 메모가 다시 저장되는 것 방지)
            if self.save_timer:
                self.after_cancel(self.save_timer)
                self.save_timer = None

            del self.memos[self.current_memo_id]
            self.save_memos()
            self.create_new_memo()
            self.refresh_sidebar()
            # 메모 삭제 후 미사용 파일 즉시 정리
            self.cleanup_unused_files()

    def load_memo_content(self, memo_id):
        """선택한 메모 내용을 에디터에 로드"""
        if memo_id in self.memos:
            # 잠긴 메모인 경우 비밀번호 확인
            if self.memos[memo_id].get("locked", False):
                password = self.memos[memo_id].get("password", "")
                password_hash = self.memos[memo_id].get("password_hash", "")
                dialog = ctk.CTkInputDialog(text="비밀번호를 입력하세요:", title="잠금된 메모")
                input_password = dialog.get_input()

                # 해시값이 있으면 해시 비교, 없으면 평문 비교 (하위 호환성)
                if password_hash:
                    input_hash = hashlib.sha256(input_password.encode()).hexdigest()
                    if input_hash != password_hash:
                        import tkinter.messagebox as messagebox
                        messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
                        return
                elif input_password != password:
                    import tkinter.messagebox as messagebox
                    messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
                    return

            # 이전 메모 버튼을 파스텔 녹색으로 변경
            if self.current_memo_id and self.current_memo_id in self.memo_buttons:
                self.memo_buttons[self.current_memo_id].configure(fg_color="#C8E6C9")

            # 리소스 정리 (메모리 누수 방지)
            self._cleanup_resources()

            self.current_memo_id = memo_id
            self.is_modified = False  # 새로 로드하면 수정되지 않은 상태
            content = self.memos[memo_id]["content"]
            rich_content = self.memos[memo_id].get("rich_content", None)

            self.textbox.delete("1.0", "end")

            # 이미지/미디어 참조 초기화
            if not hasattr(self, 'images'):
                self.images = {}
            if not hasattr(self, 'medias'):
                self.medias = {}
            if not hasattr(self, 'paint_frames'):
                self.paint_frames = []
            if not hasattr(self, 'table_widgets'):
                self.table_widgets = []

            if rich_content:
                # 서식 정보가 있는 경우 복원
                for segment in rich_content:
                    # 미디어 데이터 처리
                    if segment.get("type") == "media":
                        platform = segment.get("platform")
                        url = segment.get("url")
                        thumbnail_path = segment.get("thumbnail_path")
                        display_width = segment.get("display_width")
                        display_height = segment.get("display_height")
                        if thumbnail_path and os.path.exists(thumbnail_path):
                            self.load_media_from_path(thumbnail_path, platform, url, display_width, display_height)
                        continue

                    # 이미지 데이터 처리
                    if segment.get("type") == "image":
                        image_path = segment.get("path")
                        display_width = segment.get("display_width")
                        display_height = segment.get("display_height")
                        if image_path and os.path.exists(image_path):
                            self.load_image_from_path(image_path, display_width, display_height)
                        continue

                    # PaintFrame 데이터 처리
                    if segment.get("type") == "paint":
                        paint_path = segment.get("path")
                        width = segment.get("width", 600)
                        height = segment.get("height", 400)
                        if paint_path and os.path.exists(paint_path):
                            self.load_paint_from_path(paint_path, width, height)
                        continue

                    # TableWidget 데이터 처리
                    if segment.get("type") == "table":
                        table_data = segment.get("data")
                        if table_data:
                            self.load_table_from_data(table_data)
                        continue

                    # 일반 텍스트 처리
                    text = segment.get("text", "")
                    tags = segment.get("tags", [])

                    for tag in tags:
                        self.configure_tag_if_needed(tag) # 동적 태그 설정 복구
                    self.textbox._textbox.insert("end", text, tuple(tags))
            else:
                # 구버전 데이터 호환 (단순 텍스트)
                self.textbox.insert("1.0", content)

            # 새로 선택한 메모 버튼을 보라색으로 변경
            self.update_memo_button_color()
            self.update_status_bar()

            # 줄 번호 갱신
            self.linenumbers.redraw()

    def load_paint_from_path(self, paint_path, width, height):
        """파일 경로로부터 PaintFrame 로드 및 표시"""
        try:
            # PaintFrame 생성
            paint_frame = PaintFrame(self.textbox._textbox, width=width, height=height, use_overlay_toolbar=False)

            # 자동 저장 경로 설정
            paint_frame.auto_save_path = paint_path

            # 프로젝트 파일 로드
            if os.path.exists(paint_path):
                paint_frame.load_project_from_path(paint_path)

            # 편집 완료 상태로 설정 (툴바와 레이어 패널 숨김)
            paint_frame.finish_editing()

            # 텍스트 위젯에 삽입
            self.textbox._textbox.insert("end", "\n")
            self.textbox._textbox.window_create("end", window=paint_frame, padx=5, pady=5)
            self.textbox._textbox.insert("end", "\n")

            # PaintFrame 객체가 가비지 컬렉션되지 않도록 참조 저장
            self.paint_frames.append(paint_frame)

            logger.info(f"PaintFrame loaded from: {paint_path}")

        except Exception as e:
            logger.error(f"Failed to load paint frame: {e}", exc_info=True)

    def load_table_from_data(self, table_data):
        """표 데이터로부터 TableWidget 로드 및 표시"""
        try:
            # TableWidget 생성
            rows = table_data.get("rows", 3)
            cols = table_data.get("cols", 3)
            table_widget = TableWidget(self.textbox._textbox, rows=rows, cols=cols)

            # 표 데이터 복원
            table_widget.set_table_data(table_data)

            # 텍스트 위젯에 삽입
            self.textbox._textbox.insert("end", "\n")
            self.textbox._textbox.window_create("end", window=table_widget, padx=5, pady=5)
            self.textbox._textbox.insert("end", "\n")

            # TableWidget 객체가 가비지 컬렉션되지 않도록 참조 저장
            self.table_widgets.append(table_widget)

            logger.info(f"TableWidget loaded: {rows}x{cols}")

        except Exception as e:
            logger.error(f"Failed to load table widget: {e}", exc_info=True)

    def load_image_from_path(self, image_path, display_width=None, display_height=None):
        """파일 경로로부터 이미지 로드 및 표시"""
        try:
            from PIL import Image, ImageTk

            # 이미지 로드
            img = Image.open(image_path)
            original_width, original_height = img.width, img.height

            # 저장된 표시 크기가 있으면 사용, 없으면 기본 크기 조절
            if display_width and display_height:
                img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
            else:
                # 최대 너비 제한
                max_width = 600
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_size = (max_width, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                display_width = img.width
                display_height = img.height

            # PhotoImage로 변환
            photo = ImageTk.PhotoImage(img)

            # 파일명 추출
            filename = os.path.basename(image_path)

            # 이미지 삽입
            self.textbox._textbox.insert("end", "\n")
            image_index = self.textbox._textbox.index("insert")
            self.textbox._textbox.image_create(image_index, image=photo, name=filename)
            self.textbox._textbox.insert("end", "\n")

            # 이미지 태그 및 메타데이터
            image_tag = f"img_{filename}"
            self.textbox._textbox.tag_add(image_tag, image_index)

            self.images[image_tag] = {
                'photo': photo,
                'path': image_path,
                'original_width': original_width,
                'original_height': original_height,
                'display_width': display_width,
                'display_height': display_height,
                'index': image_index
            }

            # 더블클릭 이벤트 바인딩
            self.textbox._textbox.tag_bind(image_tag, "<Double-Button-1>",
                lambda _, tag=image_tag: self.resize_image_dialog(tag))

        except Exception as e:
            # 이미지 로드 실패 시 마커만 표시
            logger.warning(f"Failed to load image from {image_path}: {e}")
            filename = os.path.basename(image_path) if image_path else "알 수 없음"
            self.textbox._textbox.insert("end", f"[이미지 로드 실패: {filename}]\n")

    def load_media_from_path(self, thumbnail_path, platform, url, display_width, display_height):
        """저장된 미디어 썸네일 복원"""
        try:
            from PIL import Image, ImageTk

            # 썸네일 로드
            img = Image.open(thumbnail_path)
            img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)

            # PhotoImage로 변환
            photo = ImageTk.PhotoImage(img)

            # 플랫폼 이름 매핑
            platform_names = {
                'youtube': 'YouTube',
                'chzzk': '치지직',
                'twitch': 'Twitch'
            }
            platform_name = platform_names.get(platform, platform.upper())

            # 고유 이름 생성
            import time
            unique_name = f"media_{platform}_{int(time.time() * 1000)}"

            # 미디어 위젯 삽입
            self.textbox._textbox.insert("end", "\n")
            media_index = self.textbox._textbox.index("insert")
            self.textbox._textbox.image_create(media_index, image=photo, name=unique_name)
            self.textbox._textbox.insert("end", "\n")

            # 미디어 태그 및 메타데이터
            media_tag = f"media_{unique_name}"
            self.textbox._textbox.tag_add(media_tag, media_index)

            # 메타데이터 저장
            self.medias[media_tag] = {
                'photo': photo,
                'platform': platform,
                'url': url,
                'thumbnail_path': thumbnail_path,
                'display_width': display_width,
                'display_height': display_height,
                'index': media_index
            }

            # 클릭 이벤트 바인딩
            media_info_restored = {'platform': platform, 'url': url}

            # 더블클릭 우선 처리
            self.textbox._textbox.tag_bind(media_tag, "<Double-Button-1>",
                lambda e, tag=media_tag: self.on_media_double_click(e, tag))

            self.textbox._textbox.tag_bind(media_tag, "<Button-1>",
                lambda e, m=media_info_restored: self.on_media_single_click(e, m))

            logger.info(f"Media restored: {platform_name} - {url[:50]}...")

        except Exception as e:
            # 미디어 로드 실패 시 링크로 대체
            logger.warning(f"Failed to restore media from {thumbnail_path}: {e}")
            platform_display = platform.upper() if platform else "알 수 없음"
            url_display = url if url else "링크 없음"
            self.textbox._textbox.insert("end", f"[{platform_display} 미디어: {url_display}]\n")

    def on_media_single_click(self, _event, media_info):
        """미디어 싱글클릭 처리 (더블클릭과 구분)"""
        # 더블클릭 여부를 확인하기 위해 약간 대기
        if not hasattr(self, '_media_click_timer'):
            self._media_click_timer = {}

        media_key = str(media_info)

        # 이전 타이머 취소
        if media_key in self._media_click_timer:
            self.after_cancel(self._media_click_timer[media_key])

        # 300ms 후에 실행 (더블클릭이 아니면)
        self._media_click_timer[media_key] = self.after(
            300,
            lambda: self.play_media_in_app(media_info)
        )

    def on_media_double_click(self, _event, media_tag):
        """미디어 더블클릭 처리 - 크기 조절"""
        # 싱글클릭 타이머 취소
        if hasattr(self, '_media_click_timer'):
            for key in list(self._media_click_timer.keys()):
                self.after_cancel(self._media_click_timer[key])
            self._media_click_timer.clear()

        # 크기 조절 다이얼로그 표시
        self.resize_media_dialog(media_tag)
        return "break"

    def play_media_in_app(self, media_info):
        """메모장 내에서 미디어 재생"""
        platform = media_info['platform']
        url = media_info['url']

        logger.info(f"Playing {platform}: {url}")

        if platform == 'youtube':
            # YouTube embed URL 생성
            video_id = media_info.get('id')
            if not video_id:
                # URL에서 ID 추출
                import re
                match = re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', url)
                if match:
                    video_id = match.group(1)
            
            if video_id:
                # pywebview를 이용한 재생 (단일 라이브러리 사용)
                try:
                    from multiprocessing import Process
                    
                    # 현재 창의 중앙 좌표 계산하여 플레이어 위치 지정
                    window_x = self.winfo_x()
                    window_y = self.winfo_y()
                    window_width = self.winfo_width()
                    window_height = self.winfo_height()
                    
                    player_width = 800
                    player_height = 450
                    
                    pos_x = window_x + (window_width - player_width) // 2
                    pos_y = window_y + (window_height - player_height) // 2
                    
                    embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
                    p = Process(target=media_utils.run_webview, args=(embed_url, "YouTube Player", pos_x, pos_y))
                    p.daemon = True
                    p.start()
                    return
                except Exception as e:
                    logger.debug(f"Pywebview failed, falling back to browser: {e}")
        
        # YouTube가 아니거나 실패 시 브라우저로 연결
        import webbrowser
        webbrowser.open(url)

    def resize_media_dialog(self, media_tag):
        """미디어 크기 조절 다이얼로그"""
        if media_tag not in self.medias:
            return

        media_data = self.medias[media_tag]
        current_width = media_data['display_width']

        # 커스텀 다이얼로그 사용
        new_width_str = dialogs.show_custom_input_dialog(
            self,
            "미디어 크기 조절",
            f"새 너비를 입력하세요 (현재: {current_width}px):"
        )

        if not new_width_str:
            return

        try:
            new_width = int(new_width_str)
            if new_width < 100 or new_width > 1200:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", "너비는 100~1200px 사이여야 합니다.")
                return

            # 16:9 비율 유지하면서 라벨 포함 크기 계산
            new_height = int(new_width * 9 / 16)

            # 썸네일 리사이즈
            from PIL import Image, ImageTk, ImageDraw
            original_img = Image.open(media_data['thumbnail_path'])

            # 썸네일만 리사이즈
            resized_thumbnail = original_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 재생 버튼 오버레이 추가 (원본과 동일하게)
            img_with_button = resized_thumbnail.copy()
            draw = ImageDraw.Draw(img_with_button, 'RGBA')

            # 재생 버튼 (중앙)
            button_size = min(80, new_width // 6)
            center_x = new_width // 2
            center_y = new_height // 2

            # 반투명 원
            draw.ellipse(
                [center_x - button_size, center_y - button_size,
                 center_x + button_size, center_y + button_size],
                fill=(0, 0, 0, 128)
            )

            # 삼각형 (재생 버튼)
            triangle_size = button_size // 2
            draw.polygon([
                (center_x - triangle_size//2, center_y - triangle_size),
                (center_x - triangle_size//2, center_y + triangle_size),
                (center_x + triangle_size, center_y)
            ], fill=(255, 255, 255, 255))

            # 플랫폼 라벨 추가
            label_height = 30
            img_with_label = Image.new('RGB', (new_width, new_height + label_height), color='#2b2b2b')
            img_with_label.paste(img_with_button, (0, 0))

            # 라벨 텍스트는 생략 (크기만 맞춤)

            new_photo = ImageTk.PhotoImage(img_with_label)

            # 현재 이미지 위치 찾기
            all_images = self.textbox._textbox.image_names()
            target_image_name = None

            for img_name in all_images:
                # 이미지의 태그 확인
                img_index = self.textbox._textbox.index(img_name)
                tags = self.textbox._textbox.tag_names(img_index)
                if media_tag in tags:
                    target_image_name = img_name
                    break

            if target_image_name:
                # 이미지 설정 변경 (삭제 후 재생성)
                img_index = self.textbox._textbox.index(target_image_name)

                # 이미지 삭제
                self.textbox._textbox.delete(img_index)

                # 새 이미지 삽입
                self.textbox._textbox.image_create(img_index, image=new_photo, name=target_image_name)

                # 태그 다시 추가
                self.textbox._textbox.tag_add(media_tag, img_index)

                # 메타데이터 업데이트
                media_data['photo'] = new_photo
                media_data['display_width'] = new_width
                media_data['display_height'] = new_height + label_height
                media_data['index'] = img_index

                logger.info(f"Media resized: {new_width}x{new_height + label_height}")
                self.on_text_change()
            else:
                logger.warning(f"Media not found: {media_tag}")

        except ValueError:
            import tkinter.messagebox as messagebox
            messagebox.showerror("오류", "올바른 숫자를 입력하세요.")

    def on_text_change(self, event=None):
        """텍스트 변경 시 호출: 자동 저장 및 사이드바 갱신"""
        # 캐시 무효화
        self._content_cache = None

        # UI 업데이트 디바운싱 (100ms)
        if self.ui_update_timer:
            self.after_cancel(self.ui_update_timer)
        self.ui_update_timer = self.after(100, self._update_ui_elements)

        # 수정 상태로 변경 (즉시)
        if not self.is_modified:
            self.is_modified = True
            self.update_memo_button_color()

        # 저장 디바운싱 (500ms)
        if self.save_timer:
            self.after_cancel(self.save_timer)
        self.save_timer = self.after(500, self._process_save)

    def _update_ui_elements(self):
        """UI 요소 업데이트 (디바운싱됨)"""
        self.ui_update_timer = None
        self.update_status_bar()
        self.linenumbers.redraw()

    def _process_save(self):
        """실제 저장 로직 수행"""
        self.save_timer = None
        content = self.textbox.get("1.0", "end").strip()

        # 내용이 없으면 저장하지 않음 (새 메모 상태 유지)
        if not content:
            return

        # 서식 포함 데이터 직렬화
        rich_content = self.get_serialized_content()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 제목 생성 (첫 줄 혹은 앞 20자)
        title = content.split('\n')[0][:20]
        if len(content.split('\n')[0]) > 20:
            title += "..."
        if not title:
            title = "New Memo"

        # 제목 변경 여부 플래그 초기화
        title_changed = False

        # ID가 없거나, ID가 있는데 메모 목록에 없는 경우 (안전 장치)
        if self.current_memo_id is None or self.current_memo_id not in self.memos:
            # 새 메모 생성
            self.current_memo_id = str(uuid.uuid4())
            self.memos[self.current_memo_id] = {
                "title": title,
                "content": content,
                "rich_content": rich_content,
                "timestamp": timestamp,
            }
            title_changed = True  # 새 메모는 항상 사이드바 재생성 필요
        else:
            # 기존 메모 업데이트
            self.memos[self.current_memo_id]["content"] = content
            self.memos[self.current_memo_id]["rich_content"] = rich_content
            self.memos[self.current_memo_id]["timestamp"] = timestamp

            # 수동으로 설정한 제목이 아닌 경우에만 자동 생성 제목으로 업데이트
            if not self.memos[self.current_memo_id].get("custom_title", False):
                if self.memos[self.current_memo_id]["title"] != title:
                    self.memos[self.current_memo_id]["title"] = title
                    title_changed = True

        # 최적화: 제목이 변경된 경우에만 사이드바 재생성
        # 타임스탬프는 변경되지만 정렬 순서에는 영향 없음 (같은 메모 수정)
        if title_changed or self.current_memo_id not in self.memo_buttons:
            self.refresh_sidebar()
        else:
            # 현재 메모의 버튼만 업데이트 (성능 최적화)
            self._update_memo_button_text(self.current_memo_id)

        self.save_memos()

        # 저장 완료 상태로 변경
        self.is_modified = False
        self.update_memo_button_color()

    def _on_memo_click(self, memo_id):
        """메모 버튼 클릭 핸들러 (드래그 후 클릭 방지)"""
        if self.drag_data["was_dragging"]:
            self.drag_data["was_dragging"] = False
            return
        self.load_memo_content(memo_id)

    def _on_memo_click_frame(self, event, memo_id):
        """메모 프레임 클릭 핸들러 (이벤트 바인딩용)"""
        if self.drag_data["was_dragging"]:
            self.drag_data["was_dragging"] = False
            return
        self.load_memo_content(memo_id)

    def _on_drag_start(self, event, memo_id):
        """드래그 시작"""
        self.drag_data["id"] = memo_id
        self.drag_data["start_y"] = event.y_root
        self.drag_data["is_dragging"] = False
        self.drag_data["was_dragging"] = False

    def _on_drag_motion(self, event):
        """드래그 중 이동"""
        if not self.drag_data["id"]:
            return

        # 10픽셀 이상 움직였을 때만 드래그로 인식 (실수 방지)
        if not self.drag_data["is_dragging"] and abs(event.y_root - self.drag_data["start_y"]) > 10:
            self.drag_data["is_dragging"] = True
            self.configure(cursor="fleur")  # 커서 변경 (이동 모양)
            
            # 드래그 중 시각적 피드백 (색상 변경 - 파스텔 오렌지)
            if self.drag_data["id"] in self.memo_buttons:
                self.memo_buttons[self.drag_data["id"]].configure(fg_color="#FFCC80")

    def _on_drag_stop(self, event):
        """드래그 종료 및 재정렬"""
        self.configure(cursor="")  # 커서 복구
        
        if self.drag_data["is_dragging"]:
            self.drag_data["was_dragging"] = True  # 클릭 이벤트 방지 플래그 설정
            self.drag_data["is_dragging"] = False
            
            source_id = self.drag_data["id"]
            drop_y = event.y_root

            # 현재 화면에 표시된 즐겨찾기 버튼들의 위치 파악
            pinned_buttons = []
            for m_id, btn in self.memo_buttons.items():
                if self.memos[m_id].get("pinned", False):
                    pinned_buttons.append((m_id, btn))
            
            # Y좌표 순으로 정렬 (화면상 순서)
            pinned_buttons.sort(key=lambda x: x[1].winfo_rooty())

            # 드롭된 위치의 인덱스 찾기
            target_index = -1
            for i, (m_id, btn) in enumerate(pinned_buttons):
                btn_y = btn.winfo_rooty()
                btn_h = btn.winfo_height()
                # 버튼 영역 안에 들어오면 해당 위치로 이동
                if btn_y <= drop_y <= btn_y + btn_h:
                    target_index = i
                    break
            
            # 맨 아래로 드래그한 경우 처리 (마지막 버튼보다 아래에 놓았을 때)
            if target_index == -1 and pinned_buttons:
                last_btn = pinned_buttons[-1][1]
                if drop_y > last_btn.winfo_rooty() + last_btn.winfo_height():
                    target_index = len(pinned_buttons)

            if target_index != -1:
                self._reorder_pinned_memos(source_id, target_index)
            else:
                # 순서 변경이 없어도 색상 복구를 위해 갱신
                self.refresh_sidebar()

        self.drag_data["id"] = None

    def _bind_scroll_events(self, widget):
        """위젯과 그 하위 위젯들에 스크롤 이벤트를 재귀적으로 바인딩"""
        # 이벤트 바인딩 (기존 바인딩 유지하면서 추가)
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add="+")
        if self._platform.startswith("linux"):
            widget.bind("<Button-4>", self._on_mouse_wheel, add="+")
            widget.bind("<Button-5>", self._on_mouse_wheel, add="+")
        
        # 자식 위젯들에게도 적용 (재귀)
        for child in widget.winfo_children():
            self._bind_scroll_events(child)

    def _on_mouse_wheel(self, event):
        """마우스 휠 스크롤 이벤트 처리"""
        # Canvas 객체 찾기 (버전 호환성 및 안전한 접근)
        canvas = None
        if hasattr(self.scrollable_frame, "_parent_canvas"):
            canvas = self.scrollable_frame._parent_canvas
        elif hasattr(self.scrollable_frame, "canvas"):
            canvas = self.scrollable_frame.canvas
        elif hasattr(self.scrollable_frame, "_parent_frame"):
            # CustomTkinter 최신 버전 호환
            parent = self.scrollable_frame._parent_frame
            if hasattr(parent, "canvas"):
                canvas = parent.canvas

        if not canvas:
            logger.debug("Canvas not found for scrolling")
            return

        try:
            if self._platform.startswith("linux"):
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            elif self._platform == "darwin":
                # macOS 트랙패드 및 마우스 휠 지원
                delta = event.delta
                if delta == 0:
                    return
                # 트랙패드는 delta 값이 작고, 마우스 휠은 큼
                # delta 값에 따라 스크롤 양 조절
                if abs(delta) < 5:
                    # 트랙패드 (미세 조정)
                    move = -1 * delta
                else:
                    # 마우스 휠 (큰 값)
                    move = -1 * (delta / abs(delta)) * 3  # 방향만 사용, 고정 스크롤량

                canvas.yview_scroll(int(move), "units")
            else:
                # Windows
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        except Exception as e:
            logger.debug(f"Scroll error: {e}")

    def refresh_sidebar(self, filtered_memos=None):
        """사이드바의 메모 목록 버튼들을 다시 그림"""
        # 기존 버튼 제거 (CTkScrollableFrame의 내부 구조를 파괴하지 않도록 수정)
        if hasattr(self, 'memo_buttons'):
            for btn in self.memo_buttons.values():
                try:
                    btn.destroy()
                except:
                    pass
        self.memo_buttons = {}  # 버튼 딕셔너리 초기화

        # 검색 모드인 경우 필터링된 메모 사용
        memos_to_display = filtered_memos if filtered_memos is not None else self.memos

        # 고정 필터가 활성화된 경우, 고정된 메모만 표시
        if self.pin_filter_active:
            memos_to_display = {m_id: data for m_id, data in memos_to_display.items() if data.get("pinned", False)}

        # 고정된 메모와 일반 메모 분리
        pinned_memos = []
        normal_memos = []

        for m_id, data in memos_to_display.items():
            if data.get("pinned", False):
                pinned_memos.append((m_id, data))
            else:
                normal_memos.append((m_id, data))

        # 각각 최신순 정렬
        # 즐겨찾기: 1순위 사용자 지정 순서(pinned_index), 2순위 타임스탬프
        pinned_memos.sort(key=lambda item: item[1].get('timestamp', ''), reverse=True)
        pinned_memos.sort(key=lambda item: item[1].get('pinned_index', float('inf')))
        normal_memos.sort(key=lambda item: item[1].get('timestamp', ''), reverse=True)

        # 고정된 메모 먼저, 그 다음 일반 메모
        sorted_memos = pinned_memos + normal_memos

        for m_id, data in sorted_memos:
            title = data.get('title', 'No Title')
            timestamp = data.get('timestamp', '')
            tags = data.get('tags', [])
            is_pinned = data.get('pinned', False)
            is_locked = data.get('locked', False)

            # 현재 선택된 메모인지 확인
            is_current = (m_id == self.current_memo_id)

            # 색상 결정 (파스텔 톤): 현재 선택 > 저장됨
            if is_current:
                if self.is_modified:
                    fg_color = MEMO_LIST_COLORS["unsaved_bg"]
                    title_color = MEMO_LIST_COLORS["unsaved_title"]
                    info_color = MEMO_LIST_COLORS["unsaved_info"]
                    hover_color = MEMO_LIST_COLORS["unsaved_hover"]
                else:
                    fg_color = MEMO_LIST_COLORS["selected_bg"]
                    title_color = MEMO_LIST_COLORS["selected_title"]
                    info_color = MEMO_LIST_COLORS["selected_info"]
                    hover_color = MEMO_LIST_COLORS["selected_hover"]
            else:
                fg_color = MEMO_LIST_COLORS["saved_bg"]
                title_color = MEMO_LIST_COLORS["saved_title"]
                info_color = MEMO_LIST_COLORS["saved_info"]
                hover_color = MEMO_LIST_COLORS["saved_hover"]

            # 메모 아이템 프레임 생성
            item_frame = ctk.CTkFrame(
                self.scrollable_frame,
                fg_color=fg_color,
                border_width=1,
                border_color="#3E454F",
                corner_radius=6
            )
            item_frame.pack(fill="x", pady=2)

            # 제목 라벨 (굵게, 좌측 정렬)
            title_text = title
            if is_pinned: title_text = "⭐ " + title_text
            if is_locked: title_text = "🔒 " + title_text

            title_label = ctk.CTkLabel(
                item_frame,
                text=title_text,
                font=("Roboto Medium", 14, "bold"),
                anchor="w",
                justify="left",
                text_color=title_color
            )
            title_label.pack(fill="x", padx=10, pady=(5, 0))

            # 정보 라벨 (태그, 시간 - 일반 폰트, 좌측 정렬)
            info_text = ""
            if tags:
                info_text += " ".join([f"#{tag}" for tag in tags]) + "\n"
            info_text += timestamp

            info_label = ctk.CTkLabel(
                item_frame,
                text=info_text,
                font=("Roboto Medium", 12),
                text_color=info_color,
                anchor="w",
                justify="left"
            )
            info_label.pack(fill="x", padx=10, pady=(0, 5))

            # 호버 효과를 위한 데이터 저장
            item_frame._original_color = fg_color
            item_frame._hover_color = hover_color

            # 버튼 저장
            self.memo_buttons[m_id] = item_frame

            # 이벤트 바인딩 대상 위젯들
            widgets = [item_frame, title_label, info_label]

            # 호버 효과
            def on_enter(_, frame=item_frame):
                frame.configure(fg_color=frame._hover_color)

            def on_leave(_, frame=item_frame):
                frame.configure(fg_color=frame._original_color)

            for w in widgets:
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)

            # 스크롤 포커스 처리
            if hasattr(self.scrollable_frame, '_parent_canvas'):
                scroll_canvas = self.scrollable_frame._parent_canvas
                for w in widgets:
                    w.bind("<Enter>", lambda _: scroll_canvas.focus_set(), add="+")

            # 더블 클릭 이름 변경
            for w in widgets:
                w.bind("<Double-Button-1>", lambda e, i=m_id: self.rename_memo(i))

            # 우클릭 메뉴 (고정/해제)
            for w in widgets:
                w.bind("<Button-2>" if self._platform == "darwin" else "<Button-3>",
                       lambda e, i=m_id: self._show_memo_context_menu(e, i))

            # 클릭 및 드래그 이벤트
            if is_pinned:
                for w in widgets:
                    w.bind("<Button-1>", lambda e, i=m_id: self._on_drag_start(e, i))
                    w.bind("<B1-Motion>", self._on_drag_motion)
                    w.bind("<ButtonRelease-1>", self._on_drag_stop)
                    # 드래그 종료 후 클릭 처리를 위해 추가 바인딩
                    w.bind("<ButtonRelease-1>", lambda e, i=m_id: self._on_memo_click_frame(e, i), add="+")
            else:
                for w in widgets:
                    w.bind("<ButtonRelease-1>", lambda e, i=m_id: self._on_memo_click_frame(e, i))

    def _show_memo_context_menu(self, event, memo_id):
        """메모 항목 우클릭 메뉴 표시"""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0)

        is_pinned = self.memos[memo_id].get("pinned", False)

        if is_pinned:
            menu.add_command(label="⭐ 고정 해제", command=lambda: self._toggle_memo_pin(memo_id))
        else:
            menu.add_command(label="⭐ 고정", command=lambda: self._toggle_memo_pin(memo_id))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_memo_pin(self, memo_id):
        """특정 메모의 고정 상태 토글"""
        if memo_id not in self.memos:
            return

        current_pinned = self.memos[memo_id].get("pinned", False)
        self.memos[memo_id]["pinned"] = not current_pinned
        self.save_memos()
        self.refresh_sidebar()

    def _reorder_pinned_memos(self, source_id, target_index):
        """즐겨찾기 메모 순서 재정렬 및 저장"""
        # 현재 정렬된 즐겨찾기 목록 가져오기
        pinned_memos = [m_id for m_id, data in self.memos.items() if data.get("pinned", False)]
        # 기존 정렬 로직과 동일하게 정렬하여 기준점 확보
        pinned_memos.sort(key=lambda m_id: self.memos[m_id].get('timestamp', ''), reverse=True)
        pinned_memos.sort(key=lambda m_id: self.memos[m_id].get('pinned_index', float('inf')))

        # 소스 ID 제거 후 타겟 위치에 삽입
        if source_id in pinned_memos:
            pinned_memos.remove(source_id)
            if target_index >= len(pinned_memos):
                pinned_memos.append(source_id)
            else:
                pinned_memos.insert(target_index, source_id)

        # 인덱스 재할당
        for i, m_id in enumerate(pinned_memos):
            self.memos[m_id]["pinned_index"] = i

        self.save_memos()
        self.refresh_sidebar()

    def _update_memo_button_text(self, memo_id):
        """특정 메모 버튼의 텍스트만 업데이트 (성능 최적화)"""
        if memo_id not in self.memo_buttons or memo_id not in self.memos:
            return

        frame = self.memo_buttons[memo_id]
        data = self.memos[memo_id]

        title = data.get('title', 'No Title')
        timestamp = data.get('timestamp', '')
        tags = data.get('tags', [])
        is_pinned = data.get('pinned', False)
        is_locked = data.get('locked', False)

        # 제목 텍스트 구성
        title_text = title
        if is_pinned: title_text = "⭐ " + title_text
        if is_locked: title_text = "🔒 " + title_text
        
        # 정보 텍스트 구성
        info_text = ""
        if tags:
            info_text += " ".join([f"#{tag}" for tag in tags]) + "\n"
        info_text += timestamp

        # 라벨 업데이트 (순서: 제목, 정보)
        children = frame.winfo_children()
        if len(children) >= 2:
            children[0].configure(text=title_text)
            children[1].configure(text=info_text)

    def update_memo_button_color(self):
        """현재 메모의 버튼 색상을 상태에 따라 업데이트"""
        if self.current_memo_id and self.current_memo_id in self.memo_buttons:
            btn = self.memo_buttons[self.current_memo_id]
            if self.is_modified:
                btn.configure(fg_color="#FFCDD2")  # 파스텔 레드 (저장되지 않음)
            else:
                btn.configure(fg_color="#E1BEE7")  # 파스텔 퍼플 (현재 선택됨)

if __name__ == "__main__":
    app = MemoApp()
    app.mainloop()

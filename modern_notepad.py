import customtkinter as ctk
import json
import os
import uuid
from datetime import datetime
import tkinter
import tkinter.font as tkfont
from tkinter import colorchooser

# 설정
ctk.set_appearance_mode("Dark")  # 모드: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # 테마: "blue" (standard), "green", "dark-blue"

DATA_FILE = "memos.json"

class MemoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Modern Auto-Save Notepad")
        self.geometry("900x600")

        # 플랫폼 감지 (단축키에 사용)
        import platform
        self._platform = platform.system().lower()

        # 데이터 초기화
        self.memos = {}  # {uuid: {title, content, timestamp, tags, pinned, locked, password}}
        self.current_memo_id = None
        self.save_timer = None
        self.is_modified = False  # 현재 메모가 수정되었는지 여부
        self.memo_buttons = {}  # 메모 ID별 버튼 저장 (색상 업데이트용)
        self.search_mode = False  # 검색 모드 여부
        self.load_memos()

        # 현재 입력 서식 상태 추적
        self._configured_font_tags = set()  # 최적화: 이미 설정된 폰트 태그 캐싱
        self.current_input_tags = set()  # 커서 위치에서 적용할 태그들
        self.manual_format_mode = False  # 사용자가 수동으로 서식을 설정했는지 여부

        # 그리드 레이아웃 설정 (1x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 좌측 사이드바 (메모 목록) ===
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        # 검색 바
        self.search_entry = ctk.CTkEntry(
            self.sidebar_frame,
            placeholder_text="🔍 Search memos...",
            height=35
        )
        self.search_entry.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # 새 메모 버튼
        self.new_button = ctk.CTkButton(
            self.sidebar_frame,
            text="+ New Memo",
            command=self.create_new_memo,
            fg_color="#1976D2",
            hover_color="#1565C0",
            text_color="white",
            height=35
        )
        self.new_button.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")

        # 기능 버튼 프레임
        self.action_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.action_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # 즐겨찾기 버튼
        self.pin_button = ctk.CTkButton(
            self.action_frame,
            text="⭐",
            width=50,
            height=30,
            command=self.toggle_pin,
            fg_color="#FF9800"
        )
        self.pin_button.grid(row=0, column=0, padx=(0, 5))

        # 잠금 버튼
        self.lock_button = ctk.CTkButton(
            self.action_frame,
            text="🔒",
            width=50,
            height=30,
            command=self.toggle_lock,
            fg_color="#607D8B"
        )
        self.lock_button.grid(row=0, column=1, padx=(0, 5))

        # 삭제 버튼
        self.delete_button = ctk.CTkButton(
            self.action_frame,
            text="🗑",
            width=50,
            height=30,
            fg_color="#C62828",
            hover_color="#B71C1C",
            command=self.delete_memo
        )
        self.delete_button.grid(row=0, column=2)

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

        # 메모 리스트 (스크롤 가능)
        self.scrollable_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="Memos")
        self.scrollable_frame.grid(row=4, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        # 스크롤바 가시성 조절을 위한 이벤트 바인딩 (창 크기 변경 시 체크)
        self.scrollable_frame.bind("<Configure>", self._update_scrollbar_visibility)
        
        # === 우측 메인 (텍스트 에디터) ===
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # === 서식 툴바 ===
        self.toolbar_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=40)
        self.toolbar_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 10))

        # 1. 폰트 선택
        self.fonts = list(tkfont.families())
        self.fonts.sort()
        self.font_var = ctk.StringVar(value="Roboto Medium")
        self.font_combo = ctk.CTkComboBox(
            self.toolbar_frame, values=self.fonts, variable=self.font_var, width=150,
            command=self.change_font_family
        )
        self.font_combo.pack(side="left", padx=(0, 5))

        # 2. 사이즈 선택
        self.sizes = [str(s) for s in range(8, 40, 2)]
        self.size_var = ctk.StringVar(value="16")
        self.size_combo = ctk.CTkComboBox(
            self.toolbar_frame, values=self.sizes, variable=self.size_var, width=70,
            command=self.change_font_size
        )
        self.size_combo.pack(side="left", padx=(0, 10))

        # 3. 스타일 버튼들 (B, I, U, S)
        self.bold_button = ctk.CTkButton(
            self.toolbar_frame,
            text="B",
            font=("Roboto Medium", 14, "bold"),
            width=30, height=30,
            fg_color="#3E454F",
            command=self.toggle_bold
        )
        self.bold_button.pack(side="left", padx=(0, 5))

        self.italic_button = ctk.CTkButton(
            self.toolbar_frame,
            text="I",
            font=("Roboto Medium", 14, "italic"),
            width=30, height=30,
            fg_color="#3E454F",
            command=self.toggle_italic
        )
        self.italic_button.pack(side="left", padx=(0, 5))

        self.underline_button = ctk.CTkButton(
            self.toolbar_frame,
            text="U",
            font=("Roboto Medium", 14, "underline"),
            width=30, height=30,
            fg_color="#3E454F",
            command=self.toggle_underline
        )
        self.underline_button.pack(side="left", padx=(0, 5))

        self.strike_button = ctk.CTkButton(
            self.toolbar_frame,
            text="S",
            font=("Roboto Medium", 14, "overstrike"),
            width=30, height=30,
            fg_color="#3E454F",
            command=self.toggle_overstrike
        )
        self.strike_button.pack(side="left", padx=(0, 10))

        # 4. 색상 버튼
        self.color_button = ctk.CTkButton(
            self.toolbar_frame, text="Color", width=60, height=30, fg_color="#5C6BC0", command=self.change_color
        )
        self.color_button.pack(side="left", padx=(0, 10))

        # 5. 하이라이트 버튼
        self.highlight_button = ctk.CTkButton(
            self.toolbar_frame, text="Highlight", width=80, height=30, fg_color="#FFB74D", command=self.change_highlight
        )
        self.highlight_button.pack(side="left", padx=(0, 10))

        # 6. 정렬 버튼들
        self.align_left_button = ctk.CTkButton(
            self.toolbar_frame, text="⬅", width=30, height=30, fg_color="#3E454F", command=self.align_left
        )
        self.align_left_button.pack(side="left", padx=(0, 5))

        self.align_center_button = ctk.CTkButton(
            self.toolbar_frame, text="⬛", width=30, height=30, fg_color="#3E454F", command=self.align_center
        )
        self.align_center_button.pack(side="left", padx=(0, 5))

        self.align_right_button = ctk.CTkButton(
            self.toolbar_frame, text="➡", width=30, height=30, fg_color="#3E454F", command=self.align_right
        )
        self.align_right_button.pack(side="left", padx=(0, 10))

        # 7. 실행취소/다시실행 버튼
        self.undo_button = ctk.CTkButton(
            self.toolbar_frame, text="↶", width=30, height=30, fg_color="#3E454F", command=self.undo_action
        )
        self.undo_button.pack(side="left", padx=(0, 5))

        self.redo_button = ctk.CTkButton(
            self.toolbar_frame, text="↷", width=30, height=30, fg_color="#3E454F", command=self.redo_action
        )
        self.redo_button.pack(side="left", padx=(0, 10))

        # 8. 링크, 이미지, 체크리스트, 내보내기
        self.link_button = ctk.CTkButton(
            self.toolbar_frame, text="🔗", width=30, height=30, fg_color="#3E454F", command=self.insert_link
        )
        self.link_button.pack(side="left", padx=(0, 5))

        self.media_button = ctk.CTkButton(
            self.toolbar_frame, text="🎬", width=30, height=30, fg_color="#3E454F", command=self.insert_media
        )
        self.media_button.pack(side="left", padx=(0, 5))

        self.image_button = ctk.CTkButton(
            self.toolbar_frame, text="🖼", width=30, height=30, fg_color="#3E454F", command=self.insert_image
        )
        self.image_button.pack(side="left", padx=(0, 5))

        self.checklist_button = ctk.CTkButton(
            self.toolbar_frame, text="☑", width=30, height=30, fg_color="#3E454F", command=self.insert_checklist
        )
        self.checklist_button.pack(side="left", padx=(0, 5))

        self.export_button = ctk.CTkButton(
            self.toolbar_frame, text="📥", width=30, height=30, fg_color="#3E454F", command=self.export_memo
        )
        self.export_button.pack(side="left", padx=(0, 5))

        self.textbox = ctk.CTkTextbox(
            self.main_frame, 
            font=("Roboto Medium", 16),
            undo=True,
            wrap="word"
        )
        self.textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        # 키보드 이벤트 바인딩 (자동 저장용 및 서식 적용)
        # CTkTextbox의 내부 위젯에 직접 바인딩
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

        # 단축키 바인딩
        self.bind("<Command-b>" if self._platform == "darwin" else "<Control-b>", lambda _: (self.toggle_bold(), "break"))
        self.bind("<Command-i>" if self._platform == "darwin" else "<Control-i>", lambda _: (self.toggle_italic(), "break"))
        self.bind("<Command-u>" if self._platform == "darwin" else "<Control-u>", lambda _: (self.toggle_underline(), "break"))
        self.bind("<Command-z>" if self._platform == "darwin" else "<Control-z>", lambda _: (self.undo_action(), "break"))
        self.bind("<Command-Shift-z>" if self._platform == "darwin" else "<Control-y>", lambda _: (self.redo_action(), "break"))
        self.bind("<Command-f>" if self._platform == "darwin" else "<Control-f>", lambda _: (self.show_find_dialog(), "break"))
        self.bind("<Command-a>" if self._platform == "darwin" else "<Control-a>", lambda _: (self.select_all(), "break"))

        # 초기 UI 렌더링
        self.refresh_sidebar()
        self.setup_tags() # 서식 태그 설정
        self.create_new_memo() # 시작 시 새 메모 상태

    def load_memos(self):
        """JSON 파일에서 메모 불러오기"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.memos = json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
                self.memos = {}

    def save_memos(self):
        """메모를 JSON 파일에 저장"""
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memos, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")

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
        self.bold_button.configure(fg_color="#1976D2" if has_bold else "#3E454F")

        # Italic 버튼 상태
        has_italic = any(p.get("slant") == "italic" for p in parsed_font_tags)
        self.italic_button.configure(fg_color="#1976D2" if has_italic else "#3E454F")

        # Underline 버튼 상태
        has_underline = "underline" in self.current_input_tags
        self.underline_button.configure(fg_color="#1976D2" if has_underline else "#3E454F")

        # Overstrike 버튼 상태
        has_overstrike = "overstrike" in self.current_input_tags
        self.strike_button.configure(fg_color="#1976D2" if has_overstrike else "#3E454F")

    def toggle_bold(self):
        self.apply_font_attribute("weight")
        self.update_format_buttons()

    def toggle_italic(self):
        self.apply_font_attribute("slant")
        self.update_format_buttons()

    def toggle_underline(self):
        self.toggle_tag("underline")
        self.update_format_buttons()

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
                    fg_color="#C62828",
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

    def toggle_lock(self):
        """현재 메모 잠금/해제"""
        if not self.current_memo_id:
            return

        is_locked = self.memos[self.current_memo_id].get("locked", False)

        if is_locked:
            # 잠금 해제: 비밀번호 확인
            password = self.memos[self.current_memo_id].get("password", "")
            dialog = ctk.CTkInputDialog(text="비밀번호를 입력하세요:", title="잠금 해제")
            input_password = dialog.get_input()

            if input_password == password:
                self.memos[self.current_memo_id]["locked"] = False
                self.memos[self.current_memo_id]["password"] = ""
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
                self.memos[self.current_memo_id]["password"] = password
                self.save_memos()
                self.refresh_sidebar()

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
                # 이미지 저장 디렉토리 생성
                images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memo_images")
                if not os.path.exists(images_dir):
                    os.makedirs(images_dir)

                # 고유한 파일명으로 이미지 복사
                file_ext = os.path.splitext(file_path)[1]
                new_filename = f"{uuid.uuid4().hex}{file_ext}"
                copied_path = os.path.join(images_dir, new_filename)
                shutil.copy2(file_path, copied_path)

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
            except Exception as e:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", f"이미지를 불러올 수 없습니다: {str(e)}")

    def parse_media_url(self, url):
        """URL에서 미디어 정보 추출 (API 불필요)"""
        import re

        # YouTube
        youtube_patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
            r'm\.youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})'
        ]

        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                return {
                    'platform': 'youtube',
                    'id': match.group(1),
                    'url': url
                }

        # 치지직 (Chzzk)
        if 'chzzk.naver.com' in url:
            return {
                'platform': 'chzzk',
                'url': url
            }

        # Twitch
        if 'twitch.tv' in url or 'clips.twitch.tv' in url:
            return {
                'platform': 'twitch',
                'url': url
            }

        return None

    def get_thumbnail_url(self, media_info):
        """썸네일 URL 가져오기 (API 불필요)"""
        platform = media_info['platform']

        if platform == 'youtube':
            # YouTube 공개 썸네일 URL (중화질 - 항상 존재)
            return f"https://img.youtube.com/vi/{media_info['id']}/mqdefault.jpg"

        elif platform == 'chzzk' or platform == 'twitch':
            # OG 이미지 스크래핑
            try:
                import requests
                from bs4 import BeautifulSoup

                response = requests.get(media_info['url'], timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                og_image = soup.find('meta', property='og:image')

                if og_image and og_image.get('content'):
                    return og_image['content']
            except Exception as e:
                print(f"[DEBUG] Failed to get thumbnail: {e}")

        return None

    def insert_media(self):
        """미디어 링크 삽입 (YouTube, 치지직, Twitch)"""
        dialog = ctk.CTkInputDialog(text="미디어 URL을 입력하세요:\n(YouTube, 치지직, Twitch)", title="미디어 삽입")
        url = dialog.get_input()

        if not url:
            return

        # 미디어 타입 감지
        media_info = self.parse_media_url(url)

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
            from PIL import Image, ImageTk, ImageDraw
            import requests
            from io import BytesIO

            # 썸네일 다운로드
            thumbnail_url = self.get_thumbnail_url(media_info)

            if not thumbnail_url:
                import tkinter.messagebox as messagebox
                messagebox.showerror("오류", "썸네일을 가져올 수 없습니다.")
                return

            print(f"[DEBUG] Downloading thumbnail from: {thumbnail_url}")
            response = requests.get(thumbnail_url, timeout=10)
            img = Image.open(BytesIO(response.content))

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

            # 라벨 배경
            label_height = 25
            label_bg = Image.new('RGBA', (img.width, label_height), (0, 0, 0, 180))
            img_with_label = Image.new('RGBA', (img.width, img.height + label_height), (0, 0, 0, 0))
            img_with_label.paste(img, (0, 0))
            img_with_label.paste(label_bg, (0, img.height), label_bg)

            # PhotoImage로 변환
            photo = ImageTk.PhotoImage(img_with_label)

            # 썸네일 캐시 저장
            images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memo_images", "thumbnails")
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)

            cache_filename = f"{uuid.uuid4().hex}.png"
            cache_path = os.path.join(images_dir, cache_filename)
            img_with_label.save(cache_path, 'PNG')

            # 텍스트 위젯에 삽입
            current_index = self.textbox._textbox.index("insert")
            self.textbox._textbox.insert(current_index, "\n")
            image_index = self.textbox._textbox.index("insert")

            media_id = f"media_{uuid.uuid4().hex[:8]}"
            self.textbox._textbox.image_create(image_index, image=photo, name=media_id)
            self.textbox._textbox.insert("insert", f" {platform_label}\n")

            # 미디어 태그 생성
            media_tag = f"media_{media_id}"
            self.textbox._textbox.tag_add(media_tag, image_index)

            # 클릭 이벤트 - 브라우저에서 열기
            self.textbox._textbox.tag_bind(media_tag, "<Button-1>",
                lambda _: self.open_url(media_info['url']))

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
            print(f"[DEBUG] Media inserted: {media_info['platform']} - {media_info['url']}")

        except Exception as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("오류", f"미디어를 불러올 수 없습니다: {str(e)}")
            print(f"[DEBUG] Media insert error: {e}")
            import traceback
            traceback.print_exc()

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
                    print(f"[DEBUG] Link clicked: {url}")  # 디버그 로그
                    try:
                        import webbrowser
                        result = webbrowser.open(url)
                        print(f"[DEBUG] Browser open result: {result}")
                    except Exception as e:
                        print(f"[DEBUG] Error opening browser: {e}")
                        import tkinter.messagebox as messagebox
                        messagebox.showerror("오류", f"링크를 열 수 없습니다: {str(e)}")
                    return "break"

            # 3. 이미지 클릭 (향후 확장용)
            # 이미지 더블클릭은 별도 바인딩 처리

        except Exception as e:
            print(f"[DEBUG] Click handler error: {e}")

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

            if file_path.endswith(".html"):
                # HTML 형식으로 내보내기
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Roboto Medium', sans-serif; padding: 20px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <pre>{content}</pre>
</body>
</html>"""
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            elif file_path.endswith(".md"):
                # Markdown 형식으로 내보내기
                md_content = f"# {title}\n\n{content}"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
            else:
                # 일반 텍스트로 내보내기
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

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
                self.format_painter_button.configure(fg_color="#4CAF50")  # 활성화 표시
                # 마우스 클릭 이벤트 바인딩
                self.textbox._textbox.bind("<Button-1>", self.apply_copied_format, add="+")
            except tkinter.TclError:
                # 선택 영역이 없음
                pass
        else:
            # 서식 복사 모드 종료
            self.format_painter_mode = False
            self.format_painter_button.configure(fg_color="#3E454F")
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
            self.format_painter_button.configure(fg_color="#3E454F")

    def change_font_family(self, family):
        self.apply_font_attribute("family", family)

    def change_font_size(self, size):
        self.apply_font_attribute("size", size)

    def get_serialized_content(self):
        """텍스트와 태그 정보를 포함하여 직렬화 (이미지 정보 포함)"""
        content = []
        current_tags = set()
        # dump: 텍스트 위젯의 내용을 (key, value, index) 튜플 리스트로 반환
        dump_data = self.textbox._textbox.dump("1.0", "end-1c", text=True, tag=True, image=True)

        for key, value, index in dump_data:
            if key == "tagon" and value != "sel":
                current_tags.add(value)
            elif key == "tagoff" and value != "sel":
                current_tags.discard(value)
            elif key == "text":
                content.append({"text": value, "tags": list(current_tags)})
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
        return content

    def create_new_memo(self):
        """화면을 비우고 새 메모 모드로 전환"""
        # 이전 메모 버튼을 진한 녹색으로 변경
        if self.current_memo_id and self.current_memo_id in self.memo_buttons:
            self.memo_buttons[self.current_memo_id].configure(fg_color="#2E7D32")

        self.current_memo_id = None
        self.is_modified = False  # 새 메모는 수정되지 않은 상태
        self.textbox.delete("1.0", "end")
        self.current_input_tags = set()  # 서식 초기화
        self.manual_format_mode = False  # 수동 서식 모드 해제

        # 이미지 참조 초기화
        if not hasattr(self, 'images'):
            self.images = {}
        self.images.clear()

        # 미디어 참조 초기화
        if not hasattr(self, 'medias'):
            self.medias = {}
        self.medias.clear()

        self.textbox.focus()

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
            del self.memos[self.current_memo_id]
            self.save_memos()
            self.create_new_memo()
            self.refresh_sidebar()

    def load_memo_content(self, memo_id):
        """선택한 메모 내용을 에디터에 로드"""
        if memo_id in self.memos:
            # 잠긴 메모인 경우 비밀번호 확인
            if self.memos[memo_id].get("locked", False):
                password = self.memos[memo_id].get("password", "")
                dialog = ctk.CTkInputDialog(text="비밀번호를 입력하세요:", title="잠금된 메모")
                input_password = dialog.get_input()

                if input_password != password:
                    import tkinter.messagebox as messagebox
                    messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
                    return

            # 이전 메모 버튼을 진한 녹색으로 변경
            if self.current_memo_id and self.current_memo_id in self.memo_buttons:
                self.memo_buttons[self.current_memo_id].configure(fg_color="#2E7D32")

            self.current_memo_id = memo_id
            self.is_modified = False  # 새로 로드하면 수정되지 않은 상태
            content = self.memos[memo_id]["content"]
            rich_content = self.memos[memo_id].get("rich_content", None)

            self.textbox.delete("1.0", "end")

            # 이미지 참조 초기화
            if not hasattr(self, 'images'):
                self.images = {}
            self.images.clear()

            # 미디어 참조 초기화
            if not hasattr(self, 'medias'):
                self.medias = {}
            self.medias.clear()

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
            self.textbox._textbox.insert("end", f"[이미지 로드 실패: {os.path.basename(image_path)}]\n")

    def on_text_change(self, event=None):
        """텍스트 변경 시 호출: 자동 저장 및 사이드바 갱신"""
        # 수정 상태로 변경
        if not self.is_modified:
            self.is_modified = True
            self.update_memo_button_color()

        # 디바운싱: 이전에 예약된 저장이 있다면 취소하고 다시 예약
        if self.save_timer:
            self.after_cancel(self.save_timer)
        self.save_timer = self.after(500, self._process_save)

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
            # 사이드바 전체 갱신 (새 항목 추가를 위해)
            self.refresh_sidebar()
        else:
            # 기존 메모 업데이트
            current_title = self.memos[self.current_memo_id]["title"]
            self.memos[self.current_memo_id]["content"] = content
            self.memos[self.current_memo_id]["rich_content"] = rich_content
            self.memos[self.current_memo_id]["timestamp"] = timestamp

            # 수동으로 설정한 제목이 아닌 경우에만 자동 생성 제목으로 업데이트
            if not self.memos[self.current_memo_id].get("custom_title", False):
                self.memos[self.current_memo_id]["title"] = title

                # 제목이 바뀌었을 때만 사이드바 갱신 (성능 최적화)
                if current_title != title:
                    self.refresh_sidebar()

        self.save_memos()

        # 저장 완료 상태로 변경
        self.is_modified = False
        self.update_memo_button_color()

    def refresh_sidebar(self, filtered_memos=None):
        """사이드바의 메모 목록 버튼들을 다시 그림"""
        # 기존 버튼 제거
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # 버튼 딕셔너리 초기화
        self.memo_buttons = {}

        # 검색 모드인 경우 필터링된 메모 사용
        memos_to_display = filtered_memos if filtered_memos is not None else self.memos

        # 고정된 메모와 일반 메모 분리
        pinned_memos = []
        normal_memos = []

        for m_id, data in memos_to_display.items():
            if data.get("pinned", False):
                pinned_memos.append((m_id, data))
            else:
                normal_memos.append((m_id, data))

        # 각각 최신순 정렬
        pinned_memos.sort(key=lambda item: item[1].get('timestamp', ''), reverse=True)
        normal_memos.sort(key=lambda item: item[1].get('timestamp', ''), reverse=True)

        # 고정된 메모 먼저, 그 다음 일반 메모
        sorted_memos = pinned_memos + normal_memos

        for m_id, data in sorted_memos:
            title = data.get('title', 'No Title')
            timestamp = data.get('timestamp', '')
            tags = data.get('tags', [])
            is_pinned = data.get('pinned', False)
            is_locked = data.get('locked', False)

            # 표시할 텍스트 구성
            display_text = title
            if is_pinned:
                display_text = "⭐ " + display_text
            if is_locked:
                display_text = "🔒 " + display_text
            if tags:
                tags_str = " ".join([f"#{tag}" for tag in tags])
                display_text = f"{display_text}\n{tags_str}\n{timestamp}"
            else:
                display_text = f"{display_text}\n{timestamp}"

            # 현재 선택된 메모인지 확인
            is_current = (m_id == self.current_memo_id)

            # 색상 결정: 현재 선택 > 저장됨
            if is_current:
                if self.is_modified:
                    fg_color = "#DC3545"  # 빨강 (저장되지 않음)
                else:
                    fg_color = "#9C27B0"  # 보라색 (현재 선택됨)
            else:
                fg_color = "#2E7D32"  # 진한 녹색 (저장 완료)

            btn = ctk.CTkButton(
                self.scrollable_frame,
                text=display_text,
                command=lambda i=m_id: self.load_memo_content(i),
                fg_color=fg_color,
                border_width=1,
                border_color="#3E454F",
                anchor="w"
            )
            btn.pack(fill="x", pady=2)

            # 버튼 저장
            self.memo_buttons[m_id] = btn

            # 더블 클릭 시 이름 변경 이벤트 바인딩
            btn.bind("<Double-Button-1>", lambda event, i=m_id: self.rename_memo(i))

        # 스크롤바 상태 업데이트 (UI 렌더링 후 실행)
        self.after(100, self._update_scrollbar_visibility)

    def update_memo_button_color(self):
        """현재 메모의 버튼 색상을 상태에 따라 업데이트"""
        if self.current_memo_id and self.current_memo_id in self.memo_buttons:
            btn = self.memo_buttons[self.current_memo_id]
            if self.is_modified:
                btn.configure(fg_color="#DC3545")  # 빨강 (저장되지 않음)
            else:
                btn.configure(fg_color="#9C27B0")  # 보라색 (현재 선택됨)

    def _update_scrollbar_visibility(self, event=None):
        """내용이 화면에 다 들어오면 스크롤바 숨김"""
        try:
            if self.scrollable_frame._parent_canvas.yview() == (0.0, 1.0):
                self.scrollable_frame._scrollbar.grid_remove()
            else:
                self.scrollable_frame._scrollbar.grid()
        except (AttributeError, tkinter.TclError):
            # 위젯이 아직 초기화되지 않았거나 파괴됨
            pass

if __name__ == "__main__":
    app = MemoApp()
    app.mainloop()

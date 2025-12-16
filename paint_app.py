import customtkinter as ctk
import tkinter as tk
from tkinter import colorchooser, filedialog
from PIL import Image, ImageDraw, ImageTk, ImageColor, ImageGrab
import json
import zipfile
import io
import os

# UI 색상 팔레트 (modern_notepad.py와 동일)
UI_COLORS = {
    "primary": "#1976D2",          # 파란색 - 열기 등
    "secondary": "#546E7A",        # 청회색 - 일반 버튼
    "accent": "#FF9800",           # 주황색
    "danger": "#D32F2F",           # 빨간색 - 지우기
    "insert": "#5C6BC0",           # 남색 - 이미지, 캔버스 등
    "success": "#388E3C",          # 녹색 - 저장, 완료
}

class PaintFrame(tk.Frame):
    def __init__(self, master, width=980, height=600, use_overlay_toolbar=False, **kwargs):
        super().__init__(master, width=width, height=height, **kwargs)
        self.use_overlay_toolbar = use_overlay_toolbar
        
        # 설정
        self.brush_color = "black"
        self.brush_size = 2
        self.eraser_color = "white"
        self.current_tool = "pencil"  # pencil, line, rect, oval, eraser, bucket, eyedropper
        
        # 드래그 시작 좌표
        self.start_x = None
        self.start_y = None
        
        # 도형 미리보기용 ID
        self.current_shape_id = None
        
        # 캔버스 크기
        self.canvas_width = width
        self.canvas_height = height
        
        # 실행 취소/다시 실행 스택
        self.history = []
        self.redo_stack = []
        
        # 레이어 초기화
        # 레이어 구조: {'name': '이름', 'image': PIL.Image(RGBA), 'visible': True}
        self.layers = []
        self.current_layer_index = 0
        
        self.composite_image = None
        self.tk_image = None
        self.canvas_image_id = None
        
        # 레이어 드래그 데이터
        self.drag_data = None

        # 편집 모드 상태
        self.is_editing = True

        self.layer_widgets = []
        self.toolbar_window = None
        self.auto_save_path = None  # 자동 저장 경로 초기화
        self.setup_ui()

        # 초기 레이어 추가
        self.add_layer("Background", color=(255, 255, 255, 255)) # 흰색 배경 레이어

    def setup_ui(self):
        # === 메인 컨테이너 (캔버스 + 레이어 패널) ===
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # === 툴바 설정 ===
        if not self.use_overlay_toolbar:
            # 기본 모드: 상단에 팩 (높이를 2열을 위해 증가)
            self.toolbar = ctk.CTkFrame(self, height=120)
            self.toolbar.pack(side="top", fill="x", padx=10, pady=10)
            self._init_toolbar_widgets()

        # 오버레이 툴바인 경우 메인 컨테이너 생성 후 툴바 생성 (Z-order 보장)
        if self.use_overlay_toolbar:
            # 툴바를 독립된 윈도우(Toplevel)로 생성하여 캔버스 밖으로 이동 가능하게 함
            self.toolbar_window = ctk.CTkToplevel(self)
            self.toolbar_window.withdraw() # 초기화 중 깜빡임 방지
            self.toolbar_window.overrideredirect(True) # 창 테두리 제거
            self.toolbar_window.attributes("-topmost", True) # 항상 위에 표시
            self.toolbar_window.geometry("+100+100") # 초기 위치
            
            self.toolbar = ctk.CTkFrame(self.toolbar_window, height=50, corner_radius=10, border_width=1, border_color="gray")
            self.toolbar.pack(fill="both", expand=True)
            
            self._init_toolbar_widgets()
            
            # 툴바 드래그 이동 기능 (핸들로 이동됨)
            # self.toolbar.bind("<Button-1>", self._start_move_toolbar)
            # self.toolbar.bind("<B1-Motion>", self._move_toolbar)
            
            # 툴바 보이기
            self.toolbar_window.deiconify()
            
            # 부모 위젯 파괴 시 툴바 윈도우도 함께 파괴
            self.bind("<Destroy>", lambda e: self.toolbar_window.destroy() if self.toolbar_window else None)

    def _init_toolbar_widgets(self):
        # === 첫 번째 줄: 도구 및 색상 ===
        row1 = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        row1.pack(side="top", fill="x", padx=5, pady=(5, 2))

        # 드래그 핸들
        self.drag_handle = ctk.CTkLabel(row1, text="⋮⋮", width=30, cursor="fleur")
        self.drag_handle.pack(side="left", padx=(0, 5))
        self.drag_handle.bind("<Button-1>", self._start_move_toolbar)
        self.drag_handle.bind("<B1-Motion>", self._move_toolbar)

        # 도구 선택 라디오 버튼
        self.tool_var = ctk.StringVar(value="pencil")
        tools = [
            ("✏️", "pencil"),
            ("📏", "line"),
            ("⬜", "rect"),
            ("⚪", "oval"),
            ("🧽", "eraser"),
            ("🪣", "bucket"),
            ("💧", "eyedropper")
        ]

        for text, value in tools:
            btn = ctk.CTkRadioButton(
                row1,
                text=text,
                variable=self.tool_var,
                value=value,
                command=self.change_tool,
                width=50
            )
            btn.pack(side="left", padx=2)

        # 구분선
        tk.Frame(row1, width=1, bg="gray").pack(side="left", fill="y", padx=5, pady=2)

        # === 색상 팔레트 ===
        colors = [
            "black", "gray", "white", "red", "orange", "yellow",
            "green", "blue", "purple", "pink"
        ]

        for color in colors:
            btn = ctk.CTkButton(
                row1,
                text="",
                width=20,
                height=20,
                fg_color=color,
                hover_color=color,
                command=lambda c=color: self.set_color(c)
            )
            btn.pack(side="left", padx=2)

        # 현재 색상 표시 및 커스텀 색상 선택 버튼
        self.color_btn = ctk.CTkButton(
            row1,
            text="색상",
            width=60,
            fg_color=self.brush_color,
            command=self.choose_color
        )
        self.color_btn.pack(side="left", padx=5)

        # === 두 번째 줄: 브러시 크기 및 기능 버튼 ===
        row2 = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        row2.pack(side="top", fill="x", padx=5, pady=(2, 5))

        # 브러시 크기 슬라이더
        ctk.CTkLabel(row2, text="크기:", width=40).pack(side="left", padx=(35, 5))
        self.size_slider = ctk.CTkSlider(
            row2,
            from_=1,
            to=20,
            width=150,
            command=self.change_size
        )
        self.size_slider.set(self.brush_size)
        self.size_slider.pack(side="left", padx=5)

        self.size_label = ctk.CTkLabel(row2, text=str(self.brush_size), width=30)
        self.size_label.pack(side="left", padx=5)

        # 구분선
        tk.Frame(row2, width=1, bg="gray").pack(side="left", fill="y", padx=10, pady=2)

        # 기능 버튼들
        ctk.CTkButton(
            row2,
            text="저장",
            width=60,
            fg_color=UI_COLORS["success"],
            hover_color="#2E7D32",
            command=self.save_image
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            row2,
            text="열기",
            width=60,
            fg_color=UI_COLORS["primary"],
            hover_color="#1565C0",
            command=self.open_project
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            row2,
            text="이미지",
            width=60,
            fg_color=UI_COLORS["insert"],
            hover_color="#3949AB",
            command=self.import_image
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            row2,
            text="붙여넣기",
            width=70,
            fg_color=UI_COLORS["insert"],
            hover_color="#3949AB",
            command=self.paste_image
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            row2,
            text="캔버스",
            width=60,
            fg_color=UI_COLORS["secondary"],
            hover_color="#455A64",
            command=self.resize_canvas_dialog
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            row2,
            text="지우기",
            width=60,
            fg_color=UI_COLORS["danger"],
            hover_color="#B71C1C",
            command=self.clear_canvas
        ).pack(side="left", padx=2)

        # 편집 종료 버튼
        ctk.CTkButton(
            row2,
            text="완료",
            width=60,
            fg_color=UI_COLORS["success"],
            hover_color="#2E7D32",
            command=self.finish_editing
        ).pack(side="right", padx=5)

        # 1. 캔버스 영역
        self.canvas_frame = ctk.CTkFrame(self.main_container)
        self.canvas_frame.pack(side="left", fill="both", expand=True)
        
        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg="#E0E0E0", # 투명 영역 구분을 위해 회색 배경
            width=self.canvas_width,
            height=self.canvas_height,
            cursor="crosshair",
            highlightthickness=0,
            takefocus=1  # 포커스를 받을 수 있도록 설정
        )
        self.canvas.pack(fill="both", expand=True)

        # Canvas가 마우스 엔터/리브 시 포커스 관리
        def on_canvas_enter(_event):
            self.canvas.focus_set()

        def on_canvas_leave(_event):
            # Canvas를 벗어날 때 그리기 중이면 중단
            if self.start_x is not None:
                # 진행중인 그리기 완료 처리
                self.canvas.delete("temp")
                self.canvas.delete("temp_shape")
                if self.current_shape_id:
                    self.canvas.delete(self.current_shape_id)
                    self.current_shape_id = None
                self.update_canvas_view()
                self.start_x = None
                self.start_y = None

        self.canvas.bind("<Enter>", on_canvas_enter)
        self.canvas.bind("<Leave>", on_canvas_leave)

        # 2. 레이어 패널
        self.layer_panel = ctk.CTkFrame(self.main_container, width=200)
        self.layer_panel.pack(side="right", fill="y", padx=(10, 0))
        
        ctk.CTkLabel(self.layer_panel, text="레이어", font=("Arial", 16, "bold")).pack(pady=10)
        
        self.layer_list_frame = ctk.CTkScrollableFrame(self.layer_panel)
        self.layer_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkButton(self.layer_panel, text="+ 레이어 추가", command=lambda: self.add_layer()).pack(pady=5, padx=5, fill="x")
        ctk.CTkButton(self.layer_panel, text="- 레이어 삭제", command=self.delete_layer, fg_color="#C62828", hover_color="#B71C1C").pack(pady=5, padx=5, fill="x")
        
        # 이벤트 바인딩
        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw_motion)
        self.canvas.bind("<ButtonRelease-1>", self.end_draw)
        
        # 붙여넣기 단축키 바인딩 (master에 바인딩)
        # self.master.bind("<Control-v>", lambda e: self.paste_image())
        # self.master.bind("<Command-v>", lambda e: self.paste_image())

        # 실행 취소/다시 실행 단축키
        # self.master.bind("<Control-z>", lambda e: self.undo())
        # self.master.bind("<Command-z>", lambda e: self.undo())
        # self.master.bind("<Control-y>", lambda e: self.redo())
        # self.master.bind("<Command-Shift-z>", lambda e: self.redo())

    def _start_move_toolbar(self, event):
        self._start_drag_x = event.x_root
        self._start_drag_y = event.y_root
        
        if self.use_overlay_toolbar and self.toolbar_window:
            self._start_toolbar_x = self.toolbar_window.winfo_x()
            self._start_toolbar_y = self.toolbar_window.winfo_y()
        else:
            self._start_toolbar_x = self.toolbar.winfo_x()
            self._start_toolbar_y = self.toolbar.winfo_y()

    def _move_toolbar(self, event):
        deltax = event.x_root - self._start_drag_x
        deltay = event.y_root - self._start_drag_y
        
        new_x = int(self._start_toolbar_x + deltax)
        new_y = int(self._start_toolbar_y + deltay)
        
        if self.use_overlay_toolbar and self.toolbar_window:
            self.toolbar_window.geometry(f"+{new_x}+{new_y}")
        else:
            self.toolbar.place(x=new_x, y=new_y)

    def finish_editing(self):
        """편집 종료: 툴바와 레이어 패널 숨김 + 자동 저장"""
        self.is_editing = False
        if self.use_overlay_toolbar and self.toolbar_window:
            self.toolbar_window.withdraw()
        else:
            self.toolbar.pack_forget()

        self.layer_panel.pack_forget()

        # 그리기 이벤트 해제
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")

        # 재편집을 위한 더블클릭 이벤트 바인딩
        self.canvas.bind("<Double-Button-1>", self.start_editing)

        # 자동 저장: pproj 파일로 저장
        if hasattr(self, 'auto_save_path') and self.auto_save_path:
            try:
                self.save_project(self.auto_save_path)
            except Exception as e:
                print(f"Auto-save failed: {e}")

    def start_editing(self, event=None):
        """편집 시작: UI 복구"""
        self.is_editing = True
        if self.use_overlay_toolbar and self.toolbar_window:
            self.toolbar_window.deiconify()
            self.toolbar_window.attributes("-topmost", True) # 다시 위로 올림
        else:
            self.toolbar.pack(side="top", fill="x", padx=10, pady=10)
            
        self.layer_panel.pack(side="right", fill="y", padx=(10, 0))
        
        # 그리기 이벤트 복구
        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw_motion)
        self.canvas.bind("<ButtonRelease-1>", self.end_draw)
        
        # 더블클릭 이벤트 해제
        self.canvas.unbind("<Double-Button-1>")

    def change_tool(self):
        # 도구 변경 시 이전 그리기 상태 초기화
        self.start_x = None
        self.start_y = None

        # 미리보기 도형 제거
        if self.current_shape_id:
            self.canvas.delete(self.current_shape_id)
            self.current_shape_id = None

        # 임시 그리기 객체 제거
        self.canvas.delete("temp")
        self.canvas.delete("temp_shape")

        self.current_tool = self.tool_var.get()

        # 도구 변경 후 Canvas로 포커스 복귀
        self.canvas.focus_set()

    def set_color(self, color):
        self.brush_color = color
        self.color_btn.configure(fg_color=color)
        # 색상 변경 후 Canvas로 포커스 복귀
        self.canvas.focus_set()

    def choose_color(self):
        color = colorchooser.askcolor(color=self.brush_color, title="브러시 색상 선택")[1]
        if color:
            self.set_color(color)
        # 색상 선택 다이얼로그 후 Canvas로 포커스 복귀
        self.canvas.focus_set()

    def change_size(self, value):
        self.brush_size = int(value)
        self.size_label.configure(text=str(self.brush_size))
        # 크기 변경 후 Canvas로 포커스 복귀
        self.canvas.focus_set()

    def add_layer(self, name=None, color=(0, 0, 0, 0)):
        self.save_history() # 상태 저장
        
        """새 레이어 추가"""
        if name is None:
            name = f"Layer {len(self.layers)}"
        
        # RGBA 모드로 생성 (투명 배경 지원)
        image = Image.new("RGBA", (self.canvas_width, self.canvas_height), color)
        self.layers.append({'name': name, 'image': image, 'visible': True, 'locked': False})
        self.current_layer_index = len(self.layers) - 1
        
        if hasattr(self, 'layer_list_frame'):
            self.update_layer_ui()
            self.update_canvas_view()

    def delete_layer(self):
        self.save_history() # 상태 저장
        
        """현재 레이어 삭제"""
        if len(self.layers) > 1:
            del self.layers[self.current_layer_index]
            if self.current_layer_index >= len(self.layers):
                self.current_layer_index = len(self.layers) - 1
            self.update_layer_ui()
            self.update_canvas_view()

    def select_layer(self, index):
        """작업할 레이어 선택"""
        self.current_layer_index = index
        self.update_layer_selection_visuals()
        # 레이어 선택 후 Canvas로 포커스 복귀
        self.canvas.focus_set()

    def update_layer_ui(self):
        """레이어 목록 UI 갱신"""
        # 기존 위젯 삭제 (안전하게 처리)
        if hasattr(self, 'layer_widgets'):
            for _, widget in list(self.layer_widgets): # 리스트 복사본으로 순회
                try:
                    if widget.winfo_exists():
                        widget.destroy()
                except Exception:
                    pass
        self.layer_widgets = []
        
        # 부모 프레임 유효성 검사
        if not hasattr(self, 'layer_list_frame') or not self.layer_list_frame.winfo_exists():
            return
            
        # 역순으로 표시 (위쪽 레이어가 목록 상단에 오도록)
        for i in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[i]
            
            # 버튼 대신 프레임+라벨 사용 (이벤트 바인딩 신뢰성 확보)
            item_frame = ctk.CTkFrame(
                self.layer_list_frame,
                border_width=1,
                border_color="gray",
                height=30
            )
            item_frame.pack(fill="x", pady=2)
            item_frame.pack_propagate(False) # 높이 고정
            
            # 숨김/보이기 버튼
            vis_text = "👁️" if layer['visible'] else "🚫"
            vis_btn = ctk.CTkButton(
                item_frame, text=vis_text, width=25, height=25, 
                fg_color="transparent", hover_color="#555555", 
                text_color="white", # 테마에 따라 조정 가능
                command=lambda idx=i: self.toggle_visibility(idx)
            )
            vis_btn.pack(side="left", padx=2)

            # 잠금/해제 버튼
            lock_text = "🔒" if layer.get('locked', False) else "🔓"
            lock_btn = ctk.CTkButton(
                item_frame, text=lock_text, width=25, height=25, 
                fg_color="transparent", hover_color="#555555", 
                text_color="white",
                command=lambda idx=i: self.toggle_lock(idx)
            )
            lock_btn.pack(side="left", padx=2)

            label = ctk.CTkLabel(
                item_frame,
                text=layer['name']
            )
            label.pack(fill="both", expand=True, padx=5)
            
            # 이벤트 바인딩 (프레임과 라벨 모두에 적용)
            for w in [item_frame, label]:
                w.bind("<Button-1>", lambda e, idx=i: self.on_layer_drag_start(e, idx))
                w.bind("<B1-Motion>", self.on_layer_drag_motion)
                w.bind("<ButtonRelease-1>", self.on_layer_drag_stop)
                w.bind("<Double-Button-1>", lambda e, idx=i: self.rename_layer(idx))
            
            self.layer_widgets.append((i, item_frame))
            
        self.update_layer_selection_visuals()
        self.layer_list_frame.update_idletasks()

    def toggle_visibility(self, index):
        self.layers[index]['visible'] = not self.layers[index]['visible']
        self.update_layer_ui()
        self.update_canvas_view()
        # Canvas로 포커스 복귀
        self.canvas.focus_set()

    def toggle_lock(self, index):
        self.layers[index]['locked'] = not self.layers[index].get('locked', False)
        self.update_layer_ui()
        # Canvas로 포커스 복귀
        self.canvas.focus_set()

    def update_layer_selection_visuals(self):
        """레이어 선택 시각 효과만 갱신 (위젯 재생성 방지)"""
        for idx, widget_frame in self.layer_widgets:
            is_selected = (idx == self.current_layer_index)
            fg_color = "#1976D2" if is_selected else "transparent"
            text_color = "white" if is_selected else ("black" if ctk.get_appearance_mode()=="Light" else "white")
            
            widget_frame.configure(fg_color=fg_color)
            # 라벨 색상 변경
            for child in widget_frame.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(text_color=text_color)

    def on_layer_drag_start(self, event, index):
        """레이어 드래그 시작"""
        self.drag_data = {"index": index, "start_y": event.y_root}
        # 선택도 같이 수행
        self.select_layer(index)

    def on_layer_drag_motion(self, event):
        """레이어 드래그 중"""
        # 시각적 피드백은 복잡하므로 생략하거나 커서 변경
        self.configure(cursor="hand2")

    def on_layer_drag_stop(self, event):
        """레이어 드래그 종료 (순서 변경)"""
        self.configure(cursor="")
        if not self.drag_data:
            return

        source_index = self.drag_data["index"]
        drop_y = event.y_root
        target_index = source_index

        # 드롭 위치 확인
        for idx, btn in self.layer_widgets:
            btn_y = btn.winfo_rooty()
            btn_h = btn.winfo_height()
            if btn_y <= drop_y <= btn_y + btn_h:
                target_index = idx
                break
        
        if target_index != source_index:
            self.save_history() # 순서 변경 전 저장
            
            # 레이어 이동
            layer = self.layers.pop(source_index)
            self.layers.insert(target_index, layer)
            
            # 현재 선택된 레이어 인덱스 보정
            # (이동 후 선택된 레이어의 인덱스가 바뀌었을 수 있음)
            # 여기서는 단순히 이동한 레이어를 다시 선택하도록 설정
            self.current_layer_index = target_index
            
            self.update_layer_ui()
            self.update_canvas_view()
        
        self.drag_data = None

    def rename_layer(self, index):
        """레이어 이름 변경"""
        old_name = self.layers[index]['name']
        dialog = ctk.CTkInputDialog(text="새 레이어 이름:", title="레이어 이름 변경")
        new_name = dialog.get_input()
        if new_name:
            self.layers[index]['name'] = new_name
            self.update_layer_ui()

    def clear_canvas(self):
        self.save_history() # 상태 저장
        
        """현재 레이어 지우기"""
        current_layer = self.layers[self.current_layer_index]
        if not current_layer['visible'] or current_layer.get('locked', False):
            return

        # 현재 레이어를 투명하게 초기화 (배경 레이어라면 흰색 유지 필요할 수 있음)
        color = (255, 255, 255, 255) if self.current_layer_index == 0 else (0, 0, 0, 0)
        self.layers[self.current_layer_index]['image'] = Image.new("RGBA", (self.canvas_width, self.canvas_height), color)
        self.update_canvas_view()

    def save_image(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png", 
            filetypes=[
                ("PNG files", "*.png"), 
                ("JPEG files", "*.jpg"), 
                ("Paint Project", "*.pproj"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            if file_path.endswith(".pproj"):
                self.save_project(file_path)
            else:
                try:
                    # 저장 시에는 배경이 투명하면 안되므로 흰색 배경과 합성
                    self.composite_image.convert("RGB").save(file_path)
                    print(f"이미지 저장 완료: {file_path}")
                except Exception as e:
                    print(f"저장 실패: {e}")

    def save_project(self, file_path):
        """프로젝트 파일(.pproj)로 저장 (레이어 정보 보존)"""
        try:
            # 부모 디렉토리가 없으면 생성
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with zipfile.ZipFile(file_path, 'w') as zf:
                metadata = {
                    "version": "1.0",
                    "canvas_width": self.canvas_width,
                    "canvas_height": self.canvas_height,
                    "layers": []
                }
                
                for i, layer in enumerate(self.layers):
                    # 각 레이어를 개별 PNG로 저장
                    img_filename = f"layers/layer_{i}.png"
                    img_byte_arr = io.BytesIO()
                    layer['image'].save(img_byte_arr, format='PNG')
                    zf.writestr(img_filename, img_byte_arr.getvalue())
                    
                    metadata["layers"].append({
                        "name": layer['name'],
                        "visible": layer['visible'],
                        "locked": layer.get('locked', False),
                        "filename": img_filename
                    })
                
                # 메타데이터 저장
                zf.writestr('project.json', json.dumps(metadata, indent=4))
            print(f"프로젝트 저장 완료: {file_path}")
        except Exception as e:
            print(f"프로젝트 저장 실패: {e}")

    def load_project_from_path(self, file_path):
        """프로젝트 파일(.pproj)을 경로로부터 불러오기 (자동 복원용)"""
        if not file_path or not os.path.exists(file_path):
            return False

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                with zf.open('project.json') as f:
                    metadata = json.load(f)

                # 캔버스 크기 복원
                if "canvas_width" in metadata and "canvas_height" in metadata:
                    self.resize_canvas(metadata["canvas_width"], metadata["canvas_height"])

                new_layers = []
                for layer_data in metadata["layers"]:
                    with zf.open(layer_data['filename']) as f:
                        img_data = f.read()
                        image = Image.open(io.BytesIO(img_data)).convert("RGBA")
                        new_layers.append({
                            'name': layer_data['name'],
                            'image': image,
                            'visible': layer_data['visible'],
                            'locked': layer_data.get('locked', False)
                        })

                self.layers = new_layers
                self.current_layer_index = len(self.layers) - 1
                self.update_layer_ui()
                self.update_canvas_view()
                print(f"프로젝트 로드 완료: {file_path}")
                return True
        except Exception as e:
            print(f"프로젝트 로드 실패: {e}")
            return False

    def open_project(self):
        """프로젝트 파일(.pproj) 불러오기 (다이얼로그 사용)"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Paint Project", "*.pproj"), ("All files", "*.*")]
        )
        if file_path:
            self.load_project_from_path(file_path)

    def import_image(self):
        """이미지 파일 불러오기 (새 레이어)"""
        self.save_history() # 상태 저장
        
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            img = Image.open(file_path).convert("RGBA")
            
            # 캔버스 크기에 맞게 리사이즈 (비율 유지)
            img.thumbnail((self.canvas_width, self.canvas_height), Image.Resampling.LANCZOS)
            
            # 새 레이어 이미지 생성 (투명 배경)
            new_layer_img = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
            
            # 중앙 정렬하여 붙여넣기
            x = (self.canvas_width - img.width) // 2
            y = (self.canvas_height - img.height) // 2
            new_layer_img.paste(img, (x, y))
            
            # 레이어 추가
            filename = os.path.basename(file_path)
            self.layers.append({'name': filename, 'image': new_layer_img, 'visible': True, 'locked': False})
            self.current_layer_index = len(self.layers) - 1
            
            self.update_layer_ui()
            self.update_canvas_view()
        except Exception as e:
            print(f"이미지 불러오기 실패: {e}")

    def resize_canvas_dialog(self):
        """캔버스 크기 변경 다이얼로그"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("캔버스 크기 변경")
        dialog.geometry("300x250")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="너비 (Width):").pack(pady=(20, 5))
        width_entry = ctk.CTkEntry(dialog)
        width_entry.insert(0, str(self.canvas_width))
        width_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="높이 (Height):").pack(pady=5)
        height_entry = ctk.CTkEntry(dialog)
        height_entry.insert(0, str(self.canvas_height))
        height_entry.pack(pady=5)

        scale_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(dialog, text="이미지 확대/축소 (Scale)", variable=scale_var).pack(pady=10)

        def apply():
            try:
                w = int(width_entry.get())
                h = int(height_entry.get())
                if w > 0 and h > 0:
                    self.resize_canvas(w, h, scale_var.get())
                    dialog.destroy()
            except ValueError:
                pass

        ctk.CTkButton(dialog, text="적용", command=apply).pack(pady=10)

    def resize_canvas(self, width, height, scale=False):
        """캔버스 및 레이어 리사이즈"""
        self.save_history()
        
        self.canvas_width = width
        self.canvas_height = height
        self.canvas.config(width=width, height=height)
        
        for layer in self.layers:
            old_img = layer['image']
            if scale:
                new_img = old_img.resize((width, height), Image.Resampling.LANCZOS)
            else:
                new_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                # 중앙 정렬 대신 좌상단(0,0) 기준 크롭/확장
                new_img.paste(old_img, (0, 0))
            layer['image'] = new_img
            
        self.update_canvas_view()

    def pick_color(self, x, y):
        """스포이드: 캔버스에서 색상 추출"""
        if self.composite_image:
            # 좌표 범위 제한
            x = max(0, min(x, self.canvas_width - 1))
            y = max(0, min(y, self.canvas_height - 1))
            
            r, g, b, a = self.composite_image.getpixel((x, y))
            color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
            self.set_color(color)

    def paste_image(self):
        """클립보드에서 이미지 붙여넣기 (새 레이어)"""
        self.save_history() # 상태 저장
        
        try:
            img = ImageGrab.grabclipboard()
            
            # 파일 목록인 경우 첫 번째 파일을 이미지로 로드 시도
            if isinstance(img, list) and img:
                if os.path.isfile(img[0]):
                    try:
                        img = Image.open(img[0])
                    except:
                        pass

            if isinstance(img, Image.Image):
                img = img.convert("RGBA")
                
                # 캔버스 크기에 맞게 리사이즈 (비율 유지)
                img.thumbnail((self.canvas_width, self.canvas_height), Image.Resampling.LANCZOS)
                
                # 새 레이어 이미지 생성 (투명 배경)
                new_layer_img = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
                
                # 중앙 정렬하여 붙여넣기
                x = (self.canvas_width - img.width) // 2
                y = (self.canvas_height - img.height) // 2
                new_layer_img.paste(img, (x, y))
                
                # 레이어 추가
                self.layers.append({'name': "Clipboard", 'image': new_layer_img, 'visible': True, 'locked': False})
                self.current_layer_index = len(self.layers) - 1
                
                self.update_layer_ui()
                self.update_canvas_view()
        except Exception as e:
            print(f"붙여넣기 실패: {e}")

    def _capture_state(self):
        """현재 레이어 상태를 깊은 복사로 캡처"""
        captured_layers = []
        for layer in self.layers:
            captured_layers.append({
                'name': layer['name'],
                'image': layer['image'].copy(),
                'visible': layer['visible'],
                'locked': layer.get('locked', False)
            })
        return {
            'layers': captured_layers,
            'current_layer_index': self.current_layer_index
        }

    def save_history(self):
        """현재 상태를 히스토리에 저장 (변경 전 호출)"""
        if len(self.history) >= 20: # 최대 20단계 저장
            self.history.pop(0)
        
        self.history.append(self._capture_state())
        self.redo_stack.clear() # 새로운 동작이 발생하면 Redo 스택 초기화

    def undo(self):
        """실행 취소"""
        if not self.history:
            return
        
        # 현재 상태를 Redo 스택에 저장
        self.redo_stack.append(self._capture_state())
        
        # History에서 이전 상태 복원
        prev_state = self.history.pop()
        self.layers = prev_state['layers']
        self.current_layer_index = prev_state['current_layer_index']
        
        self.update_layer_ui()
        self.update_canvas_view()

    def redo(self):
        """다시 실행"""
        if not self.redo_stack:
            return
            
        # 현재 상태를 History에 저장
        self.history.append(self._capture_state())
        
        # Redo 스택에서 다음 상태 복원
        next_state = self.redo_stack.pop()
        self.layers = next_state['layers']
        self.current_layer_index = next_state['current_layer_index']
        
        self.update_layer_ui()
        self.update_canvas_view()

    def start_draw(self, event):
        current_layer = self.layers[self.current_layer_index]

        # 숨겨져 있거나 잠긴 레이어에는 그리기 불가
        if not current_layer['visible'] or current_layer.get('locked', False):
            return

        # 그리기 시작 전 상태 저장
        self.save_history()

        self.start_x = event.x
        self.start_y = event.y

        if self.current_tool == "bucket":
            self.fill_area(event.x, event.y)
        elif self.current_tool == "eyedropper":
            self.pick_color(event.x, event.y)

    def get_current_draw(self):
        """현재 레이어의 ImageDraw 객체 반환"""
        return ImageDraw.Draw(self.layers[self.current_layer_index]['image'])

    def draw_motion(self, event):
        if self.start_x is None:
            return

        # 화면에 임시로 그리기 (벡터) - 태그 'temp' 지정
        if self.current_tool == "pencil":
            self.canvas.create_line(self.start_x, self.start_y, event.x, event.y, fill=self.brush_color, width=self.brush_size, capstyle=tk.ROUND, smooth=True, tags="temp")
            
            # PIL 이미지에도 실시간으로 그리기 (연필은 점들의 연속이므로 나중에 한꺼번에 그리기 어려움)
            draw = self.get_current_draw()
            draw.line([self.start_x, self.start_y, event.x, event.y], fill=self.brush_color, width=self.brush_size)
            
            self.start_x = event.x
            self.start_y = event.y
            
        elif self.current_tool == "eraser":
            # 지우개: 화면에는 배경색(또는 흰색)으로 표시
            self.canvas.create_line(self.start_x, self.start_y, event.x, event.y, fill=self.eraser_color, width=self.brush_size * 2, capstyle=tk.ROUND, smooth=True, tags="temp")
            
            # PIL: 현재 레이어에 '지우개 색'으로 칠함 (투명 지우개 구현은 복잡하므로 덮어쓰기 방식 사용)
            # 참고: 투명하게 지우려면 픽셀 데이터 조작이 필요함. 여기서는 흰색/배경색으로 덮어쓰는 방식으로 구현.
            draw = self.get_current_draw()
            draw.line([self.start_x, self.start_y, event.x, event.y], fill=self.eraser_color, width=self.brush_size * 2)
            
            self.start_x = event.x
            self.start_y = event.y
        else:
            if self.current_shape_id:
                self.canvas.delete(self.current_shape_id)
            
            # 도형은 미리보기만 그림 (PIL에는 마우스 뗄 때 그림)
            if self.current_tool == "line":
                self.current_shape_id = self.canvas.create_line(self.start_x, self.start_y, event.x, event.y, fill=self.brush_color, width=self.brush_size, tags="temp_shape")
            elif self.current_tool == "rect":
                self.current_shape_id = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline=self.brush_color, width=self.brush_size, tags="temp_shape")
            elif self.current_tool == "oval":
                self.current_shape_id = self.canvas.create_oval(self.start_x, self.start_y, event.x, event.y, outline=self.brush_color, width=self.brush_size, tags="temp_shape")

    def end_draw(self, event):
        try:
            if self.start_x is None:
                return

            draw = self.get_current_draw()

            if self.current_tool in ["line", "rect", "oval"]:
                # 좌표 정규화 (x0 <= x1, y0 <= y1 보장)
                x0, x1 = min(self.start_x, event.x), max(self.start_x, event.x)
                y0, y1 = min(self.start_y, event.y), max(self.start_y, event.y)

                if self.current_tool == "line":
                    # 직선은 정규화 불필요
                    draw.line([self.start_x, self.start_y, event.x, event.y], fill=self.brush_color, width=self.brush_size)
                elif self.current_tool == "rect":
                    draw.rectangle([x0, y0, x1, y1], outline=self.brush_color, width=self.brush_size)
                elif self.current_tool == "oval":
                    draw.ellipse([x0, y0, x1, y1], outline=self.brush_color, width=self.brush_size)
                self.current_shape_id = None

            # 그리기 종료 후 캔버스 뷰 갱신 (임시 벡터 객체 제거 및 이미지 합성)
            self.canvas.delete("temp")
            self.canvas.delete("temp_shape")
            self.update_canvas_view()
            self.start_x = None
        except Exception as e:
            print(f"[ERROR] end_draw failed: {e}")
            import traceback
            traceback.print_exc()
            self.start_x = None  # 에러 발생해도 상태 초기화

    def fill_area(self, x, y):
        """페인트 통 (Flood Fill)"""
        current_layer = self.layers[self.current_layer_index]
        img = current_layer['image']
        
        try:
            # 색상 변환 (Hex -> RGBA)
            fill_color = ImageColor.getrgb(self.brush_color) + (255,)
            
            # Flood Fill 실행 (Pillow 기능)
            # thresh: 색상 허용 오차 (0이면 정확히 일치해야 함)
            ImageDraw.floodfill(img, (x, y), fill_color, thresh=50)
            
            self.update_canvas_view()
        except Exception as e:
            print(f"Flood fill failed: {e}")

    def update_canvas_view(self):
        """모든 레이어를 합성하여 캔버스에 표시"""
        # 배경(흰색) 생성
        base = Image.new("RGBA", (self.canvas_width, self.canvas_height), (255, 255, 255, 255))

        for layer in self.layers:
            if layer['visible']:
                base = Image.alpha_composite(base, layer['image'])

        self.composite_image = base
        self.tk_image = ImageTk.PhotoImage(self.composite_image)

        if self.canvas_image_id:
            self.canvas.itemconfig(self.canvas_image_id, image=self.tk_image)
        else:
            self.canvas_image_id = self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            self.canvas.tag_lower(self.canvas_image_id) # 이미지를 항상 맨 뒤로
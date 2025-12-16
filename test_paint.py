import customtkinter as ctk
import tkinter as tk
from tkinter import colorchooser, filedialog
from PIL import Image, ImageDraw, ImageTk, ImageColor, ImageGrab
import json
import zipfile
import io
import os

class PaintApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Test Paint App")
        self.geometry("1000x700")

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
        self.canvas_width = 980
        self.canvas_height = 600
        
        # 실행 취소/다시 실행 스택
        self.history = []
        self.redo_stack = []
        
        # 레이어 초기화
        # 레이어 구조: {'name': '이름', 'image': PIL.Image(RGBA), 'visible': True}
        self.layers = []
        self.current_layer_index = 0
        self.add_layer("Background", color=(255, 255, 255, 255)) # 흰색 배경 레이어
        
        self.composite_image = None
        self.tk_image = None
        self.canvas_image_id = None
        
        # 레이어 드래그 데이터
        self.drag_data = None

        self.layer_widgets = []
        self.setup_ui()

    def setup_ui(self):
        # === 상단 툴바 ===
        self.toolbar = ctk.CTkFrame(self, height=60)
        self.toolbar.pack(side="top", fill="x", padx=10, pady=10)

        # 도구 선택 라디오 버튼
        self.tool_var = ctk.StringVar(value="pencil")
        tools = [
            ("✏️ 연필", "pencil"),
            ("📏 직선", "line"),
            ("⬜ 사각형", "rect"),
            ("⚪ 원", "oval"),
            ("🧽 지우개", "eraser"),
            ("🪣 페인트", "bucket"),
            ("💧 스포이드", "eyedropper")
        ]

        for text, value in tools:
            btn = ctk.CTkRadioButton(
                self.toolbar, 
                text=text, 
                variable=self.tool_var, 
                value=value,
                command=self.change_tool,
                width=80
            )
            btn.pack(side="left", padx=5)

        # 구분선
        tk.Frame(self.toolbar, width=1, bg="gray").pack(side="left", fill="y", padx=10, pady=5)

        # === 색상 팔레트 ===
        self.palette_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.palette_frame.pack(side="left", padx=5)
        
        colors = [
            "black", "gray", "white", "red", "orange", "yellow", 
            "green", "blue", "purple", "pink"
        ]
        
        for color in colors:
            btn = ctk.CTkButton(
                self.palette_frame,
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
            self.toolbar, 
            text="Custom", 
            width=80, 
            fg_color=self.brush_color,
            command=self.choose_color
        )
        self.color_btn.pack(side="left", padx=10)

        # 브러시 크기 슬라이더
        ctk.CTkLabel(self.toolbar, text="크기:").pack(side="left", padx=(10, 5))
        self.size_slider = ctk.CTkSlider(
            self.toolbar, 
            from_=1, 
            to=20, 
            width=150, 
            command=self.change_size
        )
        self.size_slider.set(self.brush_size)
        self.size_slider.pack(side="left", padx=5)
        
        self.size_label = ctk.CTkLabel(self.toolbar, text=str(self.brush_size))
        self.size_label.pack(side="left", padx=5)

        # 우측 버튼 (지우기, 저장)
        ctk.CTkButton(
            self.toolbar, 
            text="모두 지우기", 
            width=80, 
            fg_color="#C62828", 
            hover_color="#B71C1C",
            command=self.clear_canvas
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            self.toolbar, 
            text="크기", 
            width=60, 
            fg_color="#5C6BC0", 
            hover_color="#3949AB",
            command=self.resize_canvas_dialog
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            self.toolbar, 
            text="열기", 
            width=80, 
            fg_color="#1976D2", 
            hover_color="#1565C0",
            command=self.open_project
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            self.toolbar, 
            text="이미지", 
            width=80, 
            fg_color="#0097A7", 
            hover_color="#00838F",
            command=self.import_image
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            self.toolbar, 
            text="붙여넣기", 
            width=80, 
            fg_color="#0097A7", 
            hover_color="#00838F",
            command=self.paste_image
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            self.toolbar, 
            text="저장", 
            width=80, 
            fg_color="#2E7D32", 
            hover_color="#1B5E20",
            command=self.save_image
        ).pack(side="right", padx=10)

        # === 메인 컨테이너 (캔버스 + 레이어 패널) ===
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 1. 캔버스 영역
        self.canvas_frame = ctk.CTkFrame(self.main_container)
        self.canvas_frame.pack(side="left", fill="both", expand=True)
        
        self.canvas = tk.Canvas(
            self.canvas_frame, 
            bg="#E0E0E0", # 투명 영역 구분을 위해 회색 배경
            width=self.canvas_width, 
            height=self.canvas_height,
            cursor="crosshair",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)
        
        # 2. 레이어 패널
        self.layer_panel = ctk.CTkFrame(self.main_container, width=200)
        self.layer_panel.pack(side="right", fill="y", padx=(10, 0))
        
        ctk.CTkLabel(self.layer_panel, text="레이어", font=("Arial", 16, "bold")).pack(pady=10)
        
        self.layer_list_frame = ctk.CTkScrollableFrame(self.layer_panel)
        self.layer_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkButton(self.layer_panel, text="+ 레이어 추가", command=lambda: self.add_layer()).pack(pady=5, padx=5, fill="x")
        ctk.CTkButton(self.layer_panel, text="- 레이어 삭제", command=self.delete_layer, fg_color="#C62828", hover_color="#B71C1C").pack(pady=5, padx=5, fill="x")
        
        self.update_layer_ui()
        self.update_canvas_view()

        # 이벤트 바인딩
        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw_motion)
        self.canvas.bind("<ButtonRelease-1>", self.end_draw)
        
        # 붙여넣기 단축키 바인딩
        self.bind("<Control-v>", lambda e: self.paste_image())
        self.bind("<Command-v>", lambda e: self.paste_image())

        # 실행 취소/다시 실행 단축키
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Command-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Command-Shift-z>", lambda e: self.redo())

    def change_tool(self):
        self.current_tool = self.tool_var.get()

    def set_color(self, color):
        self.brush_color = color
        self.color_btn.configure(fg_color=color)

    def choose_color(self):
        color = colorchooser.askcolor(color=self.brush_color, title="브러시 색상 선택")[1]
        if color:
            self.set_color(color)

    def change_size(self, value):
        self.brush_size = int(value)
        self.size_label.configure(text=str(self.brush_size))

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

    def toggle_lock(self, index):
        self.layers[index]['locked'] = not self.layers[index].get('locked', False)
        self.update_layer_ui()

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
            with zipfile.ZipFile(file_path, 'w') as zf:
                metadata = {"layers": []}
                
                for i, layer in enumerate(self.layers):
                    # 각 레이어를 개별 PNG로 저장
                    img_filename = f"layer_{i}.png"
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

    def open_project(self):
        """프로젝트 파일(.pproj) 불러오기"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Paint Project", "*.pproj"), ("All files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                with zf.open('project.json') as f:
                    metadata = json.load(f)
                
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
        except Exception as e:
            print(f"프로젝트 로드 실패: {e}")

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

        # 그리기 시작 전 상태 저장 (Text, Bucket은 즉시 적용되므로 여기서 저장)
        # Pencil, Line 등은 마우스를 뗄 때 저장하지 않고 시작할 때 저장하는 것이 일반적
        # (단, 드래그 중에는 계속 그리기 때문에 start에서 저장하는게 안전)
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
        if self.start_x is None:
            return

        draw = self.get_current_draw()
        
        if self.current_tool in ["line", "rect", "oval"]:
            if self.current_tool == "line":
                draw.line([self.start_x, self.start_y, event.x, event.y], fill=self.brush_color, width=self.brush_size)
            elif self.current_tool == "rect":
                draw.rectangle([self.start_x, self.start_y, event.x, event.y], outline=self.brush_color, width=self.brush_size)
            elif self.current_tool == "oval":
                draw.ellipse([self.start_x, self.start_y, event.x, event.y], outline=self.brush_color, width=self.brush_size)
            self.current_shape_id = None

        # 그리기 종료 후 캔버스 뷰 갱신 (임시 벡터 객체 제거 및 이미지 합성)
        self.canvas.delete("temp")
        self.canvas.delete("temp_shape")
        self.update_canvas_view()
        self.start_x = None

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

if __name__ == "__main__":
    app = PaintApp()
    app.mainloop()
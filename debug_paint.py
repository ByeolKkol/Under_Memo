import customtkinter as ctk
from paint_app import PaintFrame

class DebugApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Debug Paint")
        self.geometry("800x600")

        # PaintFrame 생성
        print("=== PaintFrame 생성 중 ===")
        self.paint = PaintFrame(self, width=600, height=400, use_overlay_toolbar=False)
        self.paint.pack(fill="both", expand=True, padx=10, pady=10)

        print(f"\n=== 초기화 완료 ===")
        print(f"레이어 수: {len(self.paint.layers)}")
        print(f"현재 레이어 인덱스: {self.paint.current_layer_index}")
        print(f"layer_list_frame 존재: {hasattr(self.paint, 'layer_list_frame')}")
        print(f"canvas_image_id: {self.paint.canvas_image_id}")
        print(f"composite_image: {self.paint.composite_image}")

        # 레이어 정보 출력
        for i, layer in enumerate(self.paint.layers):
            print(f"Layer {i}: {layer['name']}, visible={layer['visible']}, size={layer['image'].size}")

if __name__ == "__main__":
    app = DebugApp()
    app.mainloop()

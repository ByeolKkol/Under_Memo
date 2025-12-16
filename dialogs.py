import customtkinter as ctk

def show_custom_input_dialog(parent, title, prompt):
    """한글 모드 단축키를 지원하는 커스텀 입력 다이얼로그"""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("500x150")
    dialog.transient(parent)
    dialog.grab_set()

    # 결과 저장
    result = {"value": None}

    # 라벨
    label = ctk.CTkLabel(dialog, text=prompt, font=("Arial", 13))
    label.pack(pady=15)

    # 입력 필드
    entry = ctk.CTkEntry(dialog, width=450, font=("Arial", 12))
    entry.pack(pady=10)
    entry.focus()

    # 한글 모드에서도 작동하는 단축키 바인딩
    def handle_keypress(event):
        is_shortcut = (event.state & 0x8) or (event.state & 0x4)

        # 한글 모드 keycode 매핑
        if is_shortcut and event.keysym == "??":
            keycode_map = {
                134217827: 'c',  # Copy
                150995062: 'v',  # Paste
                117440632: 'x',  # Cut
                97: 'a',         # Select All
            }

            key = keycode_map.get(event.keycode)
            print(f"[DEBUG] 다이얼로그 단축키: keycode={event.keycode} -> {key}")

            if key == 'c':
                # 복사
                try:
                    sel_start = entry.index("sel.first")
                    sel_end = entry.index("sel.last")
                    text = entry.get()[sel_start:sel_end]
                    dialog.clipboard_clear()
                    dialog.clipboard_append(text)
                    print("[DEBUG] 복사 완료")
                except:
                    print("[DEBUG] 선택 영역 없음")
                return "break"

            elif key == 'v':
                # 붙여넣기
                try:
                    clip_text = dialog.clipboard_get()
                    # 선택 영역이 있으면 삭제
                    try:
                        entry.delete("sel.first", "sel.last")
                    except:
                        pass
                    # 커서 위치에 삽입
                    pos = entry.index("insert")
                    entry.insert(pos, clip_text)
                    print(f"[DEBUG] 붙여넣기 완료: {clip_text[:20]}")
                except Exception as e:
                    print(f"[DEBUG] 붙여넣기 실패: {e}")
                return "break"

            elif key == 'x':
                # 잘라내기
                try:
                    sel_start = entry.index("sel.first")
                    sel_end = entry.index("sel.last")
                    text = entry.get()[sel_start:sel_end]
                    dialog.clipboard_clear()
                    dialog.clipboard_append(text)
                    entry.delete(sel_start, sel_end)
                    print("[DEBUG] 잘라내기 완료")
                except:
                    print("[DEBUG] 선택 영역 없음")
                return "break"

            elif key == 'a':
                # 전체 선택
                entry.select_range(0, 'end')
                entry.icursor('end')
                print("[DEBUG] 전체 선택")
                return "break"

    # bind_all을 사용하여 전역 바인딩
    dialog.bind_all("<KeyPress>", handle_keypress)

    # 버튼
    def on_ok():
        result["value"] = entry.get()
        # 전역 바인딩 해제
        dialog.unbind_all("<KeyPress>")
        dialog.destroy()

    def on_cancel():
        # 전역 바인딩 해제
        dialog.unbind_all("<KeyPress>")
        dialog.destroy()

    button_frame = ctk.CTkFrame(dialog)
    button_frame.pack(pady=10)

    ok_button = ctk.CTkButton(button_frame, text="확인", command=on_ok, width=100)
    ok_button.pack(side="left", padx=5)

    cancel_button = ctk.CTkButton(button_frame, text="취소", command=on_cancel, width=100)
    cancel_button.pack(side="left", padx=5)

    # Enter/Escape 키
    entry.bind("<Return>", lambda _: on_ok())
    dialog.bind("<Escape>", lambda _: on_cancel())

    # 다이얼로그가 닫힐 때까지 대기
    dialog.wait_window()

    return result["value"]
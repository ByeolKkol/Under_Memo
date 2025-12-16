"""
표 위젯 모듈
메모장에 삽입 가능한 표 기능 제공
"""

import tkinter as tk
from tkinter import simpledialog
import customtkinter as ctk


class TableWidget(tk.Frame):
    """텍스트 편집기에 삽입 가능한 표 위젯"""

    def __init__(self, master, rows=3, cols=3, **kwargs):
        super().__init__(master, **kwargs)

        self.rows = rows
        self.cols = cols
        self.cells = []  # 2D 리스트로 셀 저장

        # 표 데이터 (행 높이, 열 너비 정보 포함)
        self.row_heights = [30] * rows  # 기본 행 높이
        self.col_widths = [100] * cols  # 기본 열 너비

        # 선택된 셀 정보
        self.selected_cells = set()  # (row, col) 튜플의 집합

        # 드래그 리사이즈 정보
        self.resize_data = {
            "active": False,
            "type": None,  # "row" 또는 "col"
            "index": None,
            "start_pos": 0
        }

        # 배경색 캐싱
        self._parent_bg = master.cget("bg")

        self.setup_ui()

    def setup_ui(self):
        """표 UI 생성"""
        # 배경 투명 설정
        self.configure(bg=self._parent_bg)

        # 메인 컨테이너
        self.container = tk.Frame(self, bg=self._parent_bg, relief=tk.FLAT, borderwidth=0)
        self.container.pack(fill="both", expand=True)

        # 크기 조절 핸들 (우하단)
        self.resize_handle = tk.Frame(
            self,
            bg="#90CAF9",
            cursor="sizing",
            width=10,
            height=10
        )
        self.resize_handle.place(relx=1.0, rely=1.0, anchor="se")

        # 크기 조절 이벤트 바인딩
        self.resize_handle.bind("<Button-1>", self.start_resize)
        self.resize_handle.bind("<B1-Motion>", self.do_resize)
        self.resize_handle.bind("<ButtonRelease-1>", self.end_resize)

        # 표 생성
        self.create_table()

    def create_table(self):
        """표 그리드 생성"""
        # 기존 셀 제거
        for widget in self.container.winfo_children():
            widget.destroy()

        self.cells = []

        for row in range(self.rows):
            row_cells = []
            for col in range(self.cols):
                # 셀 프레임 (얇은 테두리) - 배경 투명
                cell_frame = tk.Frame(
                    self.container,
                    relief=tk.FLAT,
                    bg=self._parent_bg,
                    highlightthickness=0
                )
                cell_frame.grid(
                    row=row,
                    column=col,
                    sticky="nsew",
                    padx=0,
                    pady=0
                )

                # 셀 텍스트 입력 - 테두리만 표시
                cell_text = tk.Text(
                    cell_frame,
                    width=10,
                    height=2,
                    wrap=tk.WORD,
                    relief=tk.FLAT,
                    bg=self._parent_bg,
                    font=("Roboto Medium", 12),
                    insertwidth=2,
                    insertbackground="black",
                    highlightthickness=1,
                    highlightbackground="#C0C0C0",
                    highlightcolor="#90CAF9"
                )
                cell_text.pack(fill="both", expand=True, padx=0, pady=0)

                # 우클릭 메뉴 및 셀 선택
                cell_frame.bind("<Button-2>" if tk.TkVersion >= 8.6 else "<Button-3>",
                               lambda e, r=row, c=col: self.show_context_menu(e, r, c))
                cell_frame.bind("<Control-Button-1>",
                               lambda e, r=row, c=col: self.toggle_cell_selection(r, c))

                # 셀 경계선 크기 조절 기능
                cell_text.bind("<Motion>", lambda e, r=row, c=col: self.on_cell_motion(e, r, c))
                cell_text.bind("<Button-1>", lambda e, r=row, c=col: self.on_cell_border_click(e, r, c))
                cell_text.bind("<B1-Motion>", self.on_cell_border_drag)
                cell_text.bind("<ButtonRelease-1>", self.on_cell_border_release)

                row_cells.append(cell_text)

            self.cells.append(row_cells)

        # 그리드 가중치 설정
        for row in range(self.rows):
            self.container.grid_rowconfigure(row, weight=1, minsize=self.row_heights[row])

        for col in range(self.cols):
            self.container.grid_columnconfigure(col, weight=1, minsize=self.col_widths[col])

    def toggle_cell_selection(self, row, col):
        """Ctrl+클릭으로 셀 선택/해제 토글"""
        if (row, col) in self.selected_cells:
            self.selected_cells.remove((row, col))
            if row < len(self.cells) and col < len(self.cells[row]):
                self.cells[row][col].configure(bg=self._parent_bg)
        else:
            self.selected_cells.add((row, col))
            if row < len(self.cells) and col < len(self.cells[row]):
                self.cells[row][col].configure(bg="#E3F2FD")

    def on_cell_motion(self, event, row, col):
        """셀 위에서 마우스 움직임 감지 - 경계선 근처에서 커서 변경"""
        widget = event.widget
        width = widget.winfo_width()
        height = widget.winfo_height()

        threshold = 5  # 경계선 감지 범위 (픽셀)

        # 오른쪽 경계선 근처
        if width - threshold <= event.x <= width:
            widget.configure(cursor="sb_h_double_arrow")
            return
        # 하단 경계선 근처
        elif height - threshold <= event.y <= height:
            widget.configure(cursor="sb_v_double_arrow")
            return
        else:
            widget.configure(cursor="xterm")

    def on_cell_border_click(self, event, row, col):
        """셀 경계선 클릭 - 크기 조절 시작"""
        widget = event.widget
        width = widget.winfo_width()
        height = widget.winfo_height()

        threshold = 5

        # 오른쪽 경계선 클릭
        if width - threshold <= event.x <= width and col < self.cols - 1:
            self.resize_data["active"] = True
            self.resize_data["type"] = "col"
            self.resize_data["index"] = col
            self.resize_data["start_pos"] = event.x_root
            return
        # 하단 경계선 클릭
        elif height - threshold <= event.y <= height and row < self.rows - 1:
            self.resize_data["active"] = True
            self.resize_data["type"] = "row"
            self.resize_data["index"] = row
            self.resize_data["start_pos"] = event.y_root
            return

    def on_cell_border_drag(self, event):
        """셀 경계선 드래그 - 크기 조절 중"""
        if not self.resize_data["active"]:
            return

        if self.resize_data["type"] == "col":
            # 열 너비 조절
            col_idx = self.resize_data["index"]
            dx = event.x_root - self.resize_data["start_pos"]
            new_width = max(self.col_widths[col_idx] + dx, 50)
            self.col_widths[col_idx] = new_width
            self.container.grid_columnconfigure(col_idx, minsize=new_width)
            self.resize_data["start_pos"] = event.x_root

        elif self.resize_data["type"] == "row":
            # 행 높이 조절
            row_idx = self.resize_data["index"]
            dy = event.y_root - self.resize_data["start_pos"]
            new_height = max(self.row_heights[row_idx] + dy, 30)
            self.row_heights[row_idx] = new_height
            self.container.grid_rowconfigure(row_idx, minsize=new_height)
            self.resize_data["start_pos"] = event.y_root

    def on_cell_border_release(self, event):
        """셀 경계선 드래그 종료"""
        self.resize_data["active"] = False
        self.resize_data["type"] = None
        self.resize_data["index"] = None

    def clear_selection(self):
        """선택 해제"""
        for row, col in self.selected_cells:
            if row < len(self.cells) and col < len(self.cells[row]):
                self.cells[row][col].configure(bg=self._parent_bg)

        self.selected_cells.clear()

    def highlight_selection(self):
        """선택된 셀 강조"""
        for row, col in self.selected_cells:
            if row < len(self.cells) and col < len(self.cells[row]):
                self.cells[row][col].master.configure(bg="#E3F2FD")

    def show_context_menu(self, event, row, col):
        """우클릭 컨텍스트 메뉴 표시"""
        menu = tk.Menu(self, tearoff=0)

        menu.add_command(label="행 삽입 (위)", command=lambda: self.insert_row(row, "above"))
        menu.add_command(label="행 삽입 (아래)", command=lambda: self.insert_row(row, "below"))
        menu.add_command(label="행 삭제", command=lambda: self.delete_row(row))
        menu.add_separator()
        menu.add_command(label="열 삽입 (왼쪽)", command=lambda: self.insert_col(col, "left"))
        menu.add_command(label="열 삽입 (오른쪽)", command=lambda: self.insert_col(col, "right"))
        menu.add_command(label="열 삭제", command=lambda: self.delete_col(col))
        menu.add_separator()
        menu.add_command(label="셀 병합", command=self.merge_cells)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def insert_row(self, index, position="below"):
        """행 삽입"""
        if position == "above":
            insert_idx = index
        else:
            insert_idx = index + 1

        self.rows += 1
        self.row_heights.insert(insert_idx, 30)
        self.create_table()

    def delete_row(self, index):
        """행 삭제"""
        if self.rows <= 1:
            return  # 최소 1행 유지

        self.rows -= 1
        self.row_heights.pop(index)
        self.create_table()

    def insert_col(self, index, position="right"):
        """열 삽입"""
        if position == "left":
            insert_idx = index
        else:
            insert_idx = index + 1

        self.cols += 1
        self.col_widths.insert(insert_idx, 100)
        self.create_table()

    def delete_col(self, index):
        """열 삭제"""
        if self.cols <= 1:
            return  # 최소 1열 유지

        self.cols -= 1
        self.col_widths.pop(index)
        self.create_table()

    def merge_cells(self):
        """선택된 셀 병합"""
        if len(self.selected_cells) < 2:
            return

        # 병합 범위 계산
        rows = [r for r, c in self.selected_cells]
        cols = [c for r, c in self.selected_cells]

        min_row, max_row = min(rows), max(rows)
        min_col, max_col = min(cols), max(cols)

        # 병합된 셀의 텍스트 수집
        merged_text = []
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                if row < len(self.cells) and col < len(self.cells[row]):
                    text = self.cells[row][col].get("1.0", "end-1c").strip()
                    if text:
                        merged_text.append(text)

        # 첫 번째 셀에 병합된 텍스트 설정
        if min_row < len(self.cells) and min_col < len(self.cells[min_row]):
            self.cells[min_row][min_col].delete("1.0", "end")
            self.cells[min_row][min_col].insert("1.0", " ".join(merged_text))

            # 병합 영역 설정 (rowspan, columnspan)
            self.cells[min_row][min_col].master.grid_configure(
                rowspan=max_row - min_row + 1,
                columnspan=max_col - min_col + 1
            )

            # 나머지 셀 숨기기
            for row in range(min_row, max_row + 1):
                for col in range(min_col, max_col + 1):
                    if row == min_row and col == min_col:
                        continue
                    if row < len(self.cells) and col < len(self.cells[row]):
                        self.cells[row][col].master.grid_remove()

    def start_resize(self, event):
        """크기 조절 시작"""
        self.resize_data["active"] = True
        self.resize_data["start_x"] = event.x_root
        self.resize_data["start_y"] = event.y_root
        self.resize_data["start_width"] = self.container.winfo_width()
        self.resize_data["start_height"] = self.container.winfo_height()

    def do_resize(self, event):
        """크기 조절 중"""
        if not self.resize_data["active"]:
            return

        # 변화량 계산
        dx = event.x_root - self.resize_data["start_x"]
        dy = event.y_root - self.resize_data["start_y"]

        # 새로운 크기 계산 (최소 크기 제한)
        new_width = max(self.resize_data["start_width"] + dx, self.cols * 50)
        new_height = max(self.resize_data["start_height"] + dy, self.rows * 30)

        # 컨테이너 크기 조절
        self.container.configure(width=new_width, height=new_height)
        self.configure(width=new_width, height=new_height)

        # 열 너비 비례 조정
        total_old_width = sum(self.col_widths)
        width_ratio = new_width / total_old_width if total_old_width > 0 else 1
        self.col_widths = [int(w * width_ratio) for w in self.col_widths]

        # 행 높이 비례 조정
        total_old_height = sum(self.row_heights)
        height_ratio = new_height / total_old_height if total_old_height > 0 else 1
        self.row_heights = [int(h * height_ratio) for h in self.row_heights]

        # 그리드 가중치 업데이트
        for col in range(self.cols):
            self.container.grid_columnconfigure(col, weight=1, minsize=self.col_widths[col])
        for row in range(self.rows):
            self.container.grid_rowconfigure(row, weight=1, minsize=self.row_heights[row])

    def end_resize(self, event):
        """크기 조절 종료"""
        self.resize_data["active"] = False

    def get_table_data(self):
        """표 데이터 가져오기 (직렬화용)"""
        data = {
            "rows": self.rows,
            "cols": self.cols,
            "row_heights": self.row_heights,
            "col_widths": self.col_widths,
            "cells": []
        }

        for row in range(self.rows):
            row_data = []
            for col in range(self.cols):
                if row < len(self.cells) and col < len(self.cells[row]):
                    text = self.cells[row][col].get("1.0", "end-1c")
                    row_data.append(text)
                else:
                    row_data.append("")
            data["cells"].append(row_data)

        return data

    def set_table_data(self, data):
        """표 데이터 설정 (역직렬화용)"""
        self.rows = data.get("rows", 3)
        self.cols = data.get("cols", 3)
        self.row_heights = data.get("row_heights", [30] * self.rows)
        self.col_widths = data.get("col_widths", [100] * self.cols)

        self.create_table()

        # 셀 데이터 복원
        cells_data = data.get("cells", [])
        for row in range(min(self.rows, len(cells_data))):
            for col in range(min(self.cols, len(cells_data[row]))):
                if row < len(self.cells) and col < len(self.cells[row]):
                    self.cells[row][col].delete("1.0", "end")
                    self.cells[row][col].insert("1.0", cells_data[row][col])

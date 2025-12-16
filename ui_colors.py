"""
UI 색상 팔레트 모듈
메모장 애플리케이션의 모든 색상을 중앙 관리
"""

# UI 색상 팔레트
UI_COLORS = {
    # Primary Actions (주요 작업)
    "primary": "#1976D2",          # 파란색 - 새 메모, 저장 등

    # Secondary Actions (보조 작업)
    "secondary": "#546E7A",        # 청회색 - 일반 버튼

    # Accent (강조)
    "accent": "#FF9800",           # 주황색 - 고정, 하이라이트 등

    # Danger (위험)
    "danger": "#D32F2F",           # 빨간색 - 삭제

    # Text Format (텍스트 서식)
    "text_format": "#607D8B",      # 회청색 - Bold, Italic 등

    # Insert (삽입)
    "insert": "#5C6BC0",           # 남색 - 링크, 이미지, 그림판

    # Neutral
    "neutral": "#78909C",          # 회색 - 비활성 상태

    # Success
    "success": "#388E3C",          # 녹색 - 완료, 확인
}

# 사이드바 전용 파스텔 색상 팔레트
PASTEL_COLORS = {
    "primary": "#90CAF9",          # 파스텔 블루 - 새 메모
    "accent": "#FFCC80",           # 파스텔 오렌지 - 고정
    "secondary": "#B0BEC5",        # 파스텔 그레이 - 잠금
    "danger": "#EF9A9A",           # 파스텔 레드 - 삭제
}

# 메모 목록 색상 팔레트
MEMO_LIST_COLORS = {
    # 저장되지 않은 메모 (현재 선택 + 수정됨)
    "unsaved_bg": "#FFCDD2",       # 밝은 파스텔 레드
    "unsaved_title": "#D32F2F",    # 부드러운 빨강
    "unsaved_info": "#E57373",     # 밝은 빨강
    "unsaved_hover": "#EF9A9A",    # 호버 시 더 진한 색

    # 저장된 메모 (현재 선택)
    "selected_bg": "#E1BEE7",      # 밝은 파스텔 퍼플
    "selected_title": "#8E24AA",   # 부드러운 보라
    "selected_info": "#AB47BC",    # 밝은 보라
    "selected_hover": "#CE93D8",   # 호버 시 더 진한 색

    # 저장 완료 메모 (선택되지 않음)
    "saved_bg": "#C8E6C9",         # 밝은 파스텔 그린
    "saved_title": "#388E3C",      # 부드러운 녹색
    "saved_info": "#66BB6A",       # 밝은 녹색
    "saved_hover": "#A5D6A7",      # 호버 시 더 진한 색
}

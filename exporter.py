def export_file(file_path, title, content):
    """파일 형식에 따라 메모 내용 저장"""
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
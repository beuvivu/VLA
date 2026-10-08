"""Dựng lại shell từ nguồn chuẩn, giữ nguyên dữ liệu bên trong mọi trang."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from ui_theme import write_stylesheet
    write_stylesheet(ROOT / 'docs')
    subprocess.run([sys.executable, str(ROOT / 'scripts/extract_critical_css.py')], check=True)
    # Process mới sau khi critical CSS được sinh, tránh cache module cũ.
    subprocess.run([sys.executable, '-c', '''
from pathlib import Path
from page_output import write_page
for path in sorted(Path("docs").glob("*.html")):
    write_page(path, path.read_text(encoding="utf-8"))
print("Đã đồng bộ shell cho mọi trang HTML")
'''], cwd=ROOT, env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'src')}, check=True)


if __name__ == '__main__':
    main()

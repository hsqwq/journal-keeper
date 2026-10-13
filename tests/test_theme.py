import re
from pathlib import Path

from jk.theme import PALETTE, THEME

SRC = Path(__file__).parent.parent / "src" / "jk"
# 终端调色板颜色名会被主题改写（如 magenta 显示成深蓝），源码里禁止直接使用
NAMED = r"(black|red|green|yellow|blue|magenta|cyan|white|bright_\w+|dim)"


def test_no_palette_color_names_in_source():
    pattern = re.compile(rf'(style\s*=\s*"[^"]*\b{NAMED}\b|"\s*{NAMED}\s*"|\[(bold )?{NAMED}\])')
    hits = []
    for path in SRC.glob("*.py"):
        if path.name == "theme.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.name}:{n}: {line.strip()}")
    assert hits == []


def test_palette_uses_fixed_hex_colors():
    for name, style in PALETTE.items():
        assert re.search(r"#[0-9a-f]{6}", style), name
        assert f"jk.{name}" in THEME.styles

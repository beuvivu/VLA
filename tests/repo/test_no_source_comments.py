from __future__ import annotations

import ast
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOQA = re.compile(r"# noqa: [A-Z]+[0-9]+(?:, [A-Z]+[0-9]+)*")
HTML_MARKERS = {"<!-- SNAPSHOT:BEGIN -->", "<!-- SNAPSHOT:END -->"}


def tracked(*patterns: str) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *patterns, ":!docs/**", ":!data/**", ":!vietlott/data/**", ":!vietlott/reports/**"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [ROOT / name for name in out]


def python_comments(source: str) -> list[str]:
    found = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        if tok.start[0] == 1 and tok.string.startswith("#!"):
            continue
        if NOQA.fullmatch(tok.string):
            continue
        found.append(f"{tok.start[0]}: {tok.string}")
    for node in ast.walk(ast.parse(source)):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            for stmt in body if isinstance(body, list) else []:
                if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    found.append(f"{stmt.lineno}: chuỗi đứng riêng")
    return found


_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^") | {""}
_REGEX_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield"}


def js_comments(code: str) -> list[str]:
    found, i, n, last = [], 0, len(code), ""
    stack: list[str] = []
    while i < n:
        ch = code[i]
        if ch in "'\"":
            j = i + 1
            while j < n and code[j] != ch:
                j += 2 if code[j] == "\\" else 1
            i, last = j + 1, "a"
            continue
        if ch == "`" or (ch == "}" and stack and stack[-1] == "`"):
            if ch == "}":
                stack.pop()
            j = i + 1
            while j < n and code[j] != "`" and not code.startswith("${", j):
                j += 2 if code[j] == "\\" else 1
            if code.startswith("${", j):
                stack.append("`")
                i = j + 2
                last = "("
                continue
            i, last = j + 1, "a"
            continue
        if ch == "{":
            stack.append("{")
        elif ch == "}" and stack:
            stack.pop()
        if code.startswith("//", i) or code.startswith("/*", i):
            end = code.find("\n", i) if code.startswith("//", i) else code.find("*/", i) + 2
            end = n if end <= 0 else end
            text = code[i:end]
            if "eslint-disable" not in text:
                found.append(f"{code.count(chr(10), 0, i) + 1}: {text.strip()[:60]}")
            i = end
            continue
        if ch == "/":
            word = re.search(r"([A-Za-z_$][\w$]*)\s*$", code[max(0, i - 20):i])
            if last in _REGEX_BEFORE or (word and word.group(1) in _REGEX_WORDS):
                j, in_class = i + 1, False
                while j < n and (code[j] != "/" or in_class) and code[j] != "\n":
                    if code[j] == "\\":
                        j += 1
                    elif code[j] == "[":
                        in_class = True
                    elif code[j] == "]":
                        in_class = False
                    j += 1
                i, last = j + 1, "a"
                continue
        if not ch.isspace():
            last = ch if not (ch.isalnum() or ch in "_$") else "a"
            if last == "a":
                word = re.match(r"[A-Za-z_$][\w$]*", code[i:])
                if word and word.group(0) in _REGEX_WORDS:
                    last = ""
                    i += len(word.group(0))
                    continue
        i += 1
    return found


def css_comments(css: str) -> list[str]:
    found, i, n = [], 0, len(css)
    while i < n:
        if css[i] in "'\"":
            q, j = css[i], i + 1
            while j < n and css[j] != q:
                j += 2 if css[j] == "\\" else 1
            i = j + 1
            continue
        if css.startswith("/*", i):
            found.append(f"{css.count(chr(10), 0, i) + 1}: {css[i:i + 40]}")
            i = css.find("*/", i) + 2 or n
            continue
        i += 1
    return found


def hash_comments(text: str) -> list[str]:
    return [f"{k}: {ln.strip()[:60]}" for k, ln in enumerate(text.splitlines(), start=1)
            if ln.lstrip().startswith("#") and not ln.lstrip().startswith("#!")]


def html_comments(text: str) -> list[str]:
    return [m.group(0)[:60] for m in re.finditer(r"<!--.*?-->", text, re.S) if m.group(0) not in HTML_MARKERS]


def test_the_comment_rules_catch_every_kind_on_samples() -> None:
    assert python_comments("x = 1  # vì sao\n") == ["1: # vì sao"]
    assert python_comments('def f():\n    """Làm gì."""\n    return 1\n') == ["2: chuỗi đứng riêng"]
    assert python_comments("#!/usr/bin/env python3\nimport os  # noqa: F401\ns = '# không phải chú thích'\n") == []
    assert python_comments("import os  # noqa: F401 vì đăng ký tên\n") != []
    assert js_comments("const a = 1; // giải thích\n") == ["1: // giải thích"]
    assert js_comments("/* khối */ const b = 2;\n") != []
    assert js_comments('const u = "http://x"; const r = /\\/\\//g; const t = `a ${b} // chữ`;\n') == []
    assert js_comments('const t = `a ${f({k: 1})}`; // sau\n') == ["1: // sau"]
    assert js_comments('const u = "http://x"; const r = /\\/\\*/g; const d = a / b / c;\n') == []
    assert js_comments("// eslint-disable-next-line no-control-regex\nconst x = /\\x00/;\n") == []
    assert css_comments('a { content: "/* không */"; }\n/* có */\n') == ['2: /* có */\n']
    assert hash_comments("on:\n  # giải thích\n  push:\n#!/bin/bash\n") == ["2: # giải thích"]
    assert html_comments("<!-- SNAPSHOT:BEGIN -->x<!-- giải thích -->") == ["<!-- giải thích -->"]


@pytest.mark.parametrize(
    ("patterns", "check", "minimum"),
    [
        (("*.py",), python_comments, 500),
        (("*.js", "*.mjs"), js_comments, 50),
        (("*.css",), css_comments, 20),
        (("*.html", "*.j2"), html_comments, 4),
        ((".github/*.yml", ".github/workflows/*.yml", "*.sh", "*.toml", "requirements*.txt", "*/requirements*.txt",
          ".gitignore", "*/.gitignore", "*Makefile", "*Dockerfile", "*/.env.example", "vietlott/docker-compose.yml"),
         hash_comments, 30),
    ],
    ids=["python", "js", "css", "html", "yaml-shell-config"],
)
def test_no_source_file_carries_comments(patterns, check, minimum) -> None:
    files = tracked(*patterns)
    assert len(files) >= minimum
    offenders = {}
    for path in files:
        found = check(path.read_text(encoding="utf-8"))
        if found:
            offenders[path.relative_to(ROOT).as_posix()] = found[:3]
    assert offenders == {}

"""In tập gói mà các workflow cài thẳng bằng `pip install` nhưng requirements không có, cho job kiểm lỗ hổng.

`dependency-audit.yml` cài requirements của VLA rồi `pip install -r` đúng đầu ra của script này trước khi chạy
`pip-audit`, để mọi gói chạy trên runner đều bị chấm (04-11-2026, ba góp ý Codex trên PR #206: playwright của
ci.yml, playwright cài trần ở inspect-reference-*, build của vlm-release.yml).

Mỗi dòng một yêu cầu: `gói==bản` khi workflow ghim, tên trần khi không ghim — khi ấy workflow cài bản mới nhất
lúc chạy, nên job kiểm cũng chấm bản mới nhất. Chỉ đọc lệnh thật trong `run:` của từng bước (bỏ dòng chú thích);
bỏ cài từ requirements (`-r`), dự án cục bộ (`.`, `-e ".[…]"`) và mọi cờ. Gói đã có trong requirements*.txt thì
bỏ: job đã cài đúng bản ghim ấy.

`--engine-extras` in các phần tuỳ chọn của engine `vietlott/` mà workflow cài (`-e ".[dev,ml]"` trong bước chạy ở
`vietlott`), nối bằng dấu phẩy, để job engine cài và chấm đúng chừng ấy — góp ý Codex thứ tư: xgboost/lightgbm
của job ML trong vlm-ci.yml từng lọt khỏi phép kiểm.

Chạy: `python scripts/ops/audit_install_set.py [--engine-extras]` (chỉ đọc, in ra stdout).
"""
from __future__ import annotations

import argparse
import re
import shlex
from collections.abc import Iterator
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = "vietlott"
#: Cờ của `pip install` mang theo một đối số riêng (không phải tên gói).
TAKES_VALUE = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
               "--extra-index-url", "-f", "--find-links", "-t", "--target", "--prefix", "--root"}
COMMAND = re.compile(r"\s*(?:python3?\s+-m\s+)?pip3?\s+install\s+(.*)$")
PACKAGE = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)(\[[^\]]*\])?(==[^\s,;]+)?")
LOCAL_EXTRAS = re.compile(r"\.\[([A-Za-z0-9_,-]+)\]")


def requirement_names(root: Path = ROOT) -> set[str]:
    """Tên gói (chữ thường) khai trong mọi requirements*.txt ở gốc kho."""
    names: set[str] = set()
    for path in root.glob("requirements*.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", line.split("#", 1)[0])
            if match and not line.lstrip().startswith("-"):
                names.add(match.group(1).lower())
    return names


def install_commands(run: str) -> Iterator[list[str]]:
    """Đối số (đã tách như shell) của từng lệnh `pip install` trong một khối `run:`; bỏ dòng chú thích."""
    for raw in run.replace("\\\n", " ").splitlines():
        if raw.strip().startswith("#"):
            continue
        for part in re.split(r"&&|\|\||;", raw):
            match = COMMAND.match(part)
            if not match:
                continue
            try:
                yield shlex.split(match.group(1), comments=True)
            except ValueError:
                continue


def install_tokens(run: str) -> list[str]:
    """Đối số gói của mọi lệnh `pip install` trong một khối `run:` (không gồm cờ, `-r`, dự án cục bộ)."""
    tokens: list[str] = []
    for words in install_commands(run):
        skip = False
        for word in words:
            if skip:
                skip = False
                continue
            if word in TAKES_VALUE:
                skip = True
                continue
            if word.startswith(("-", ".", "/", "$")):
                continue
            tokens.append(word)
    return tokens


def workflow_steps(root: Path = ROOT) -> Iterator[tuple[str, dict]]:
    """(thư mục chạy, bước) của mọi bước có `run:` trong mọi workflow; thư mục theo luật của GitHub."""
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        top = ((document.get("defaults") or {}).get("run") or {}).get("working-directory", "")
        for job in (document.get("jobs") or {}).values():
            job = job or {}
            here = ((job.get("defaults") or {}).get("run") or {}).get("working-directory", top)
            for step in job.get("steps") or []:
                if step.get("run"):
                    yield str(step.get("working-directory", here)), step


def extra_requirements(root: Path = ROOT) -> list[str]:
    """Yêu cầu cài thêm cho job kiểm: gói workflow cài mà requirements không có; bản ghim thắng tên trần."""
    known = requirement_names(root)
    found: dict[str, str] = {}
    for _, step in workflow_steps(root):
        for token in install_tokens(str(step["run"])):
            match = PACKAGE.fullmatch(token)
            if not match or match.group(1).lower() in known:
                continue
            name = match.group(1).lower()
            if match.group(3):
                found[name] = match.group(1) + match.group(3)
            else:
                found.setdefault(name, match.group(1))
    return sorted(found.values(), key=str.lower)


def engine_extras(root: Path = ROOT) -> list[str]:
    """Phần tuỳ chọn của engine mà workflow cài: `.[a,b]` trong lệnh cài của bước chạy ở `vietlott`."""
    extras: set[str] = set()
    for directory, step in workflow_steps(root):
        if directory.strip("./") != ENGINE_DIR:
            continue
        for words in install_commands(str(step["run"])):
            for word in words:
                match = LOCAL_EXTRAS.fullmatch(word)
                if match:
                    extras.update(part.strip() for part in match.group(1).split(",") if part.strip())
    return sorted(extras)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine-extras", action="store_true",
                        help="in phần tuỳ chọn của engine vietlott/ mà workflow cài, nối bằng dấu phẩy")
    args = parser.parse_args(argv)
    print(",".join(engine_extras()) if args.engine_extras else "\n".join(extra_requirements()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

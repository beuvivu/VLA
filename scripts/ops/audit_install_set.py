from __future__ import annotations

import argparse
import re
import shlex
from collections.abc import Iterator
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = "vietlott"
TAKES_VALUE = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
               "--extra-index-url", "-f", "--find-links", "-t", "--target", "--prefix", "--root"}
COMMAND = re.compile(r"\s*(?:python3?\s+-m\s+)?pip3?\s+install\s+(.*)$")
PACKAGE = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)(\[[^\]]*\])?(==[^\s,;]+)?")
LOCAL_EXTRAS = re.compile(r"\.\[([A-Za-z0-9_,-]+)\]")


def requirement_names(root: Path = ROOT) -> set[str]:
    names: set[str] = set()
    for path in root.glob("requirements*.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", line.split("#", 1)[0])
            if match and not line.lstrip().startswith("-"):
                names.add(match.group(1).lower())
    return names


def install_commands(run: str) -> Iterator[list[str]]:
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-extras", action="store_true",
                        help="in phần tuỳ chọn của engine vietlott/ mà workflow cài, nối bằng dấu phẩy")
    args = parser.parse_args(argv)
    print(",".join(engine_extras()) if args.engine_extras else "\n".join(extra_requirements()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Dựng bản đồ mắt xích của mọi workflow từ chính YAML, ghi vào tài liệu vận hành và kiểm nó.

Workflow nối nhau qua bốn kiểu mắt xích, và GitHub im lặng khi một mắt xích gãy:

* `workflow_run` theo TÊN (`name:`) của workflow nguồn — tên gõ sai thì không bao giờ chạy;
* gọi API `actions/workflows/<tệp>/dispatches` theo TÊN TỆP — đổi tên tệp là đứt;
* `repository_dispatch` do bộ hẹn giờ ngoài (cron-job.org) gửi theo `event_type`;
* `schedule` (cron, giờ UTC) và `push` lọc theo đường dẫn.

`python3 scripts/ops/workflow_map.py --write` dựng lại khối giữa hai dấu mốc trong
`documentation/operations/workflow-map.md`; `--check` (mặc định) báo lệch và thoát 1.
`tests/repo/test_workflow_map.py` dùng cùng mô hình để buộc mọi mắt xích trỏ vào thứ có thật.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
DOC = ROOT / "documentation" / "operations" / "workflow-map.md"
START, END = "<!-- workflow-map:start -->", "<!-- workflow-map:end -->"
_API_DISPATCH = re.compile(r"actions/workflows/([\w.-]+\.ya?ml)/dispatches")
# Ba lối ghi `main` của kho: lệnh git trực tiếp, trình đẩy trang của VLA, rào xuất bản của engine.
_COMMIT_MARKERS = ("push_generated_site.py", "persist_site.py persist")
_CALL_DISPATCH = re.compile(r"""\bdispatch\(\s*["']([\w.-]+\.ya?ml)["']""")


@dataclass
class Workflow:
    file: str
    name: str
    events: list[str]
    crons: list[str] = field(default_factory=list)
    follows: list[str] = field(default_factory=list)       # tên workflow nguồn của workflow_run
    dispatch_types: list[str] = field(default_factory=list)  # repository_dispatch (bộ hẹn giờ ngoài)
    push_paths: int = 0
    dispatches: list[str] = field(default_factory=list)    # tệp workflow được gọi qua API
    commits: bool = False
    deploys_pages: bool = False


def _events(document: dict) -> dict:
    on = document.get(True, document.get("on")) or {}
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {event: None for event in on}
    return on


def load(folder: Path = WORKFLOWS) -> dict[str, Workflow]:
    out = {}
    for path in sorted(folder.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        document = yaml.safe_load(text)
        on = _events(document)
        run = on.get("workflow_run") or {}
        repo = on.get("repository_dispatch") or {}
        push = on.get("push") or {}
        out[path.name] = Workflow(
            file=path.name,
            name=str(document.get("name", path.name)),
            events=sorted(on),
            crons=[str(item["cron"]) for item in on.get("schedule") or []],
            follows=list(run.get("workflows") or []),
            dispatch_types=list(repo.get("types") or []) if isinstance(repo, dict) else [],
            push_paths=len(push.get("paths") or []) if isinstance(push, dict) else 0,
            dispatches=sorted(set(_API_DISPATCH.findall(text)) | set(_CALL_DISPATCH.findall(text))),
            commits=any(marker in text for marker in _COMMIT_MARKERS) or re.search(r"\bgit push\b", text) is not None,
            deploys_pages="actions/upload-pages-artifact@" in text,
        )
    return out


def broken_links(workflows: dict[str, Workflow]) -> list[str]:
    """Mọi mắt xích trỏ vào thứ không có thật, hoặc vòng lặp kích hoạt."""
    by_name = {w.name: w for w in workflows.values()}
    problems = []
    for w in workflows.values():
        for source in w.follows:
            if source not in by_name:
                problems.append(f"{w.file}: workflow_run theo '{source}' — không workflow nào mang tên ấy")
        for target in w.dispatches:
            if target not in workflows:
                problems.append(f"{w.file}: gọi {target} qua API — tệp không tồn tại")
            elif "workflow_dispatch" not in workflows[target].events:
                problems.append(f"{w.file}: gọi {target} qua API — {target} không khai workflow_dispatch")
    edges = {w.file: set(w.dispatches) for w in workflows.values()}
    for w in workflows.values():
        for source in w.follows:
            if source in by_name:
                edges[by_name[source].file].add(w.file)
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        state[node] = 1
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == 1:
                problems.append("vòng kích hoạt: " + " → ".join([*trail, node, nxt]))
            elif nxt in edges and not state.get(nxt):
                visit(nxt, [*trail, node])
        state[node] = 2

    for node in sorted(edges):
        if not state.get(node):
            visit(node, [])
    return problems


def _node(file: str) -> str:
    return re.sub(r"\W", "_", file.removesuffix(".yml"))


def render(workflows: dict[str, Workflow]) -> str:
    by_name = {w.name: w for w in workflows.values()}
    lines = ["```mermaid", "flowchart LR", '  ext(["Bộ hẹn giờ ngoài · cron-job.org"])']
    linked = set()
    for w in workflows.values():
        for kind in w.dispatch_types:
            lines.append(f"  ext -- {kind} --> {_node(w.file)}")
            linked.add(w.file)
        for target in w.dispatches:
            lines.append(f"  {_node(w.file)} -. API .-> {_node(target)}")
            linked |= {w.file, target}
        for source in w.follows:
            if source in by_name:
                lines.append(f"  {_node(by_name[source].file)} -- workflow_run --> {_node(w.file)}")
                linked |= {w.file, by_name[source].file}
    for file in sorted(linked):
        lines.insert(3, f'  {_node(file)}["{file}"]')
    lines += ["```", "", "| Workflow | Tên | Kích hoạt | Kích hoạt tiếp | Ghi `main` | Triển khai Pages |",
              "| --- | --- | --- | --- | --- | --- |"]
    followers: dict[str, list[str]] = {}
    for w in workflows.values():
        for source in w.follows:
            if source in by_name:
                followers.setdefault(by_name[source].file, []).append(f"`{w.file}` (workflow_run)")
    for w in workflows.values():
        trigger = []
        if w.crons:
            trigger.append("cron " + ", ".join(f"`{c}`" for c in w.crons))
        if w.dispatch_types:
            trigger.append("hẹn giờ ngoài " + ", ".join(f"`{t}`" for t in w.dispatch_types))
        if w.follows:
            trigger.append("sau " + ", ".join(f"«{s}»" for s in w.follows))
        if "push" in w.events:
            trigger.append(f"push ({w.push_paths} bộ lọc đường dẫn)" if w.push_paths else "push")
        trigger += [e for e in ("pull_request", "workflow_dispatch") if e in w.events]
        nxt = [f"`{t}` (API)" for t in w.dispatches] + followers.get(w.file, [])
        lines.append(f"| `{w.file}` | {w.name} | {'; '.join(trigger)} | {', '.join(nxt) or '—'} | "
                     f"{'có' if w.commits else '—'} | {'có' if w.deploys_pages else '—'} |")
    return "\n".join(lines) + "\n"


def updated_document(text: str, workflows: dict[str, Workflow]) -> str:
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return f"{before}{START}\n{render(workflows)}{END}{after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="ghi lại khối bản đồ trong tài liệu")
    args = parser.parse_args(argv)
    workflows = load()
    problems = broken_links(workflows)
    for problem in problems:
        print("[LỖI]", problem)
    text = DOC.read_text(encoding="utf-8")
    fresh = updated_document(text, workflows)
    if args.write:
        DOC.write_text(fresh, encoding="utf-8")
    elif fresh != text:
        print(f"[LỆCH] {DOC.relative_to(ROOT)} chưa khớp workflow; chạy lại với --write")
        return 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

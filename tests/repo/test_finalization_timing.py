"""Trang kết quả hằng ngày phải có kết quả ngay sau khi live xác minh, không chờ phân tích.

Đo ngày 12-10-2026 (lượt 38243236688), khi hoàn tất còn là MỘT job:

* 18:31:48 live xác minh và gọi update-data (``reason=live_verified``);
* 18:32:43 → 18:35:33 vòng chờ quay khống: ``sync.py --cutoff 18:35`` coi kỳ hôm nay
  "chưa xong" nên không lấy gì; lấy thật chỉ mất 12 giây;
* 18:36:06 → 18:40:44 pipeline thống kê/AI/ML, rồi mới triển khai Pages lúc 18:41:20.

Cũng tối ấy update-data còn chạy thêm NĂM lượt cho cùng kỳ (mỗi lượt live-results thấy kỳ đã
xác minh lại gọi), mỗi lượt ~8 phút; ba lượt viết lại dự báo LOTO đã công bố cho kỳ 13-10 dù sổ
kết quả không đổi.

Các phép kiểm dưới đây chạy nguyên khối ``run:`` lấy từ YAML; chỉ thay ``sync.py`` (ghi lại
tham số) và đồng hồ ngủ (``sitecustomize`` đẩy đồng hồ giả thay vì ngủ thật).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/update-data.yml"
VN = ZoneInfo("Asia/Ho_Chi_Minh")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="cần bash")


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _step(job: str, key: str) -> dict:
    for step in _jobs()[job]["steps"]:
        if key in (step.get("id"), step.get("name")):
            return step
    raise AssertionError(f"không thấy bước {key!r} trong job {job!r}")


def _needs(job: dict) -> set[str]:
    needs = job.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


#: Không ngủ thật: ``time.sleep`` đẩy đồng hồ đơn điệu giả, nên hạn chờ 15 phút của bước chờ
#: kết quả chuẩn trôi qua trong tích tắc nếu kết quả không bao giờ tới.
SITECUSTOMIZE = """
import time
_clock = [0.0]
def _sleep(seconds):
    _clock[0] += seconds
time.sleep = _sleep
time.monotonic = lambda: _clock[0]
"""

#: ``sync.py`` giả: ghi lại tham số, rồi làm như sync thật LÚC 18:32 giờ VN — chỉ lấy kỳ hôm
#: nay khi mốc cutoff không muộn hơn 18:32, nếu không thì kỳ mới nhất là hôm qua.
FAKE_SYNC = """
import json, sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

args = sys.argv[1:]
with open("sync_calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\\n")
cutoff = args[args.index("--cutoff") + 1]
today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
latest = today if cutoff <= "18:32" else today - timedelta(days=1)
Path("data/xsmb.csv").write_text("date,special\\n" + latest.isoformat() + ",12345\\n", encoding="utf-8")
Path("data/source_audit.json").write_text(
    json.dumps({latest.isoformat(): {"accepted": True, "agreement": 1}}), encoding="utf-8"
)
"""


class Runner:
    """Một thư mục làm việc giả cho khối ``run:`` của update-data."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        (tmp / "data" / "predict").mkdir(parents=True)
        (tmp / "src" / "ingest").mkdir(parents=True)
        (tmp / "src" / "ingest" / "sync.py").write_text(FAKE_SYNC, encoding="utf-8")
        (tmp / "site").mkdir()
        (tmp / "site" / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        (tmp / "bin").mkdir()
        shim = tmp / "bin" / "python"
        shim.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        self.today = datetime.now(VN).date()

    def stored(self, day) -> None:
        (self.tmp / "data" / "xsmb.csv").write_text(
            f"date,special\n{day.isoformat()},12345\n", encoding="utf-8"
        )

    def predicted(self, day, modes=("loto", "de")) -> None:
        for mode in modes:
            (self.tmp / "data" / "predict" / f"predict_next_{mode}_all_{day.isoformat()}.csv").write_text(
                "number,prob\n00,0.01\n", encoding="utf-8"
            )

    def run(self, job: str, step_key: str, *, event: str, reason: str = "manual") -> dict[str, str]:
        step = _step(job, step_key)
        script = self.tmp / "step.sh"
        script.write_text(step["run"], encoding="utf-8")
        output = self.tmp / "github_output"
        output.write_text("", encoding="utf-8")
        env = {
            **os.environ,
            "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "PYTHONPATH": str(self.tmp / "site"),
            "GITHUB_OUTPUT": str(output),
            "EVENT_NAME": event,
            "DISPATCH_REASON": reason,
            "TZ": "Asia/Ho_Chi_Minh",
        }
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=self.tmp, env=env, capture_output=True, text=True, timeout=120, check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return dict(
            line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line
        )

    def sync_calls(self) -> list[list[str]]:
        path = self.tmp / "sync_calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- Mốc cutoff của lượt live_verified ---------------------------------------


def test_a_live_verified_run_fetches_today_at_once(tmp_path: Path) -> None:
    """Live đã xác minh kỳ hôm nay; sync phải lấy ngay chứ không chờ mốc 18:35."""
    runner = Runner(tmp_path)
    runner.stored(runner.today - timedelta(days=1))
    out = runner.run("canonical", "canonical", event="workflow_dispatch", reason="live_verified")
    assert out["ready"] == "true"
    assert out["target"] == runner.today.isoformat()
    calls = runner.sync_calls()
    assert len(calls) == 1, f"lấy được ngay ở lượt đầu, không quay vòng chờ: {calls}"
    assert calls[0][calls[0].index("--cutoff") + 1] == "00:00"


def test_other_runs_keep_the_1835_cutoff(tmp_path: Path) -> None:
    """Lượt lịch và lượt phục hồi KHÔNG có bằng chứng live: kỳ hôm nay xong khi đã qua 18:35."""
    runner = Runner(tmp_path)
    runner.stored(runner.today - timedelta(days=3))
    runner.run("canonical", "canonical", event="repository_dispatch")
    calls = runner.sync_calls()
    assert calls, "phải gọi sync"
    assert {c[c.index("--cutoff") + 1] for c in calls} == {"18:35"}


# --- Bỏ lượt hoàn tất lặp lại -------------------------------------------------


def test_a_repeated_live_verified_call_skips_only_the_pipeline(tmp_path: Path) -> None:
    """Kỳ đã có dự báo kỳ sau: pipeline không chạy lại, nhưng lượt chạy KHÔNG bị bỏ cả lượt.

    Hai tệp dự báo chỉ chứng minh phân tích đã xong, không chứng minh Pages hay hậu kiểm đã
    thành công; bỏ cả lượt thì một lần triển khai hỏng không còn đường tự thử lại.
    """
    runner = Runner(tmp_path)
    runner.stored(runner.today)
    runner.predicted(runner.today + timedelta(days=1))
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert out["run"] == "true"
    assert out["finalized"] == "true"
    assert out["reason"] == "already-finalized"


@pytest.mark.parametrize("missing", ["loto", "de"])
def test_a_live_verified_call_runs_in_full_when_the_pipeline_did_not_finish(
    tmp_path: Path, missing: str
) -> None:
    """Kết quả đã chốt nhưng chưa có dự báo kỳ sau (pipeline hỏng giữa chừng): chạy lại đủ."""
    runner = Runner(tmp_path)
    runner.stored(runner.today)
    runner.predicted(runner.today + timedelta(days=1), modes=[m for m in ("loto", "de") if m != missing])
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert (out["run"], out["finalized"]) == ("true", "false")


def test_a_live_verified_call_for_a_new_draw_runs_in_full(tmp_path: Path) -> None:
    """Dự báo cho HÔM NAY có từ tối qua; nó không được làm lượt hôm nay bị coi là đã xong."""
    runner = Runner(tmp_path)
    runner.stored(runner.today - timedelta(days=1))
    runner.predicted(runner.today)
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert (out["run"], out["finalized"]) == ("true", "false")


def test_a_manual_run_always_runs_in_full(tmp_path: Path) -> None:
    """Lượt gọi tay luôn chạy đủ, kể cả khi kỳ mà guard nhắm tới đã hoàn tất trọn vẹn."""
    runner = Runner(tmp_path)
    now = datetime.now(VN)
    # Đúng mốc guard tính cho lượt không phải live_verified: qua 18:35 là hôm nay.
    target = runner.today if now.time() >= time(18, 35) else runner.today - timedelta(days=1)
    runner.stored(target)
    runner.predicted(target + timedelta(days=1))
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="manual")
    assert out["target"] == target.isoformat()
    assert (out["run"], out["finalized"]) == ("true", "false")


# --- Điều kiện chạy của từng job, đánh giá như GitHub ---------------------------
#
# Soi chuỗi trong ``if:`` không thấy được một dấu ngoặc đặt sai. Bộ đánh giá dưới đây dịch
# đúng tập con cú pháp mà các điều kiện này dùng (``always()``, ``==``, ``!=``, ``&&``, ``||``,
# ngoặc, chuỗi, tham chiếu ``needs.*``/``github.*``) sang Python rồi tính trên từng kịch bản.

_TOKEN = re.compile(
    r"\s+|'[^']*'|\b(?:needs|github)(?:\.[A-Za-z0-9_-]+)+|\btrue\b|\bfalse\b"
    r"|always\(\)|&&|\|\||==|!=|[()]"
)
_PYTHON = {"true": "True", "false": "False", "always()": "True", "&&": " and ", "||": " or "}


def _condition(job: str):
    raw = _jobs()[job]["if"].strip()
    assert raw.startswith("${{") and raw.endswith("}}"), raw
    body = raw[3:-2].strip()
    parts: list[str] = []
    pos = 0
    while pos < len(body):
        match = _TOKEN.match(body, pos)
        assert match, f"cú pháp ngoài tập con đã hỗ trợ ở vị trí {pos}: {body[pos:]!r}"
        token = match.group(0)
        if token.startswith(("needs.", "github.")):
            parts.append(f"ctx[{token!r}]")
        else:
            parts.append(_PYTHON.get(token, token))
        pos = match.end()
    expr = "".join(parts)
    needs = _needs(_jobs()[job])
    # Không có always() thì GitHub ngầm thêm success(): mọi job được cần phải thành công.
    implicit = "always()" not in body

    def evaluate(ctx: dict) -> bool:
        if implicit and any(ctx[f"needs.{n}.result"] != "success" for n in needs):
            return False
        return bool(eval(expr, {"__builtins__": {}}, {"ctx": ctx}))  # noqa: S307

    return evaluate


def _ctx(
    *, ready: str, finalized: str, update: str, publish: str = "success", canonical: str = "success"
) -> dict:
    return {
        "github.event.repository.private": False,
        "needs.canonical.result": canonical,
        "needs.canonical.outputs.canonical_ready": ready,
        "needs.canonical.outputs.finalized": finalized,
        "needs.update.result": update,
        "needs.publish-results.result": publish,
    }


SCENARIOS = {
    # tên: (ngữ cảnh, publish-results, update, deploy-pages, trigger-post-finalization)
    "kỳ mới": (_ctx(ready="true", finalized="false", update="success"), True, True, True, True),
    "đã xong, chạy lại": (_ctx(ready="true", finalized="true", update="skipped", publish="skipped"),
                          False, False, True, True),
    "pipeline hỏng": (_ctx(ready="true", finalized="false", update="failure"), True, True, False, False),
    "chưa có kết quả": (_ctx(ready="false", finalized="false", update="skipped", publish="skipped"),
                        False, False, False, False),
    "kết quả trước hỏng": (_ctx(ready="true", finalized="false", update="success", publish="failure"),
                           True, True, True, True),
    # Guard đã ghi finalized=true rồi một bước sau của canonical hỏng: không được triển khai.
    "canonical hỏng sau guard": (_ctx(ready="", finalized="true", update="skipped", publish="skipped",
                                      canonical="failure"), False, False, False, False),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_each_job_runs_exactly_when_it_should(name: str) -> None:
    ctx, publish, update, deploy, trigger = SCENARIOS[name]
    got = tuple(
        _condition(job)(ctx)
        for job in ("publish-results", "update", "deploy-pages", "trigger-post-finalization")
    )
    assert got == (publish, update, deploy, trigger), name


# --- Trang kết quả đi trước pipeline -------------------------------------------


def test_the_results_pages_do_not_wait_for_the_analytics_pipeline() -> None:
    jobs = _jobs()
    publish = jobs["publish-results"]
    assert _needs(publish) == {"canonical"}, "chờ job update là chờ ~5 phút pipeline"
    assert _needs(jobs["update"]) == {"canonical"}
    build = "\n".join(step.get("run", "") for step in publish["steps"])
    order = [
        "src/soi_cau/position_bridges.py",
        "src/pages/build_landing_page.py",
        "src/pages/build_fun_prediction.py",
        "src/pages/build_traditional_results.py",
    ]
    positions = [build.index(script) for script in order]
    assert positions == sorted(positions), "cầu vị trí → trang chủ → bảng mô phỏng"
    uses = [step.get("uses", "") for step in publish["steps"]]
    assert any(u.startswith("actions/deploy-pages@") for u in uses)
    assert "git push" not in build, "bản kết quả không commit; pipeline commit bản đầy đủ"


def test_the_full_deploy_comes_after_the_results_deploy() -> None:
    """Hai lượt triển khai trong cùng một lượt chạy: bản đầy đủ phải là bản sau cùng."""
    assert {"update", "publish-results"} <= _needs(_jobs()["deploy-pages"])


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        ("canonical", {"contents": "write"}),
        ("update", {"contents": "write"}),
        ("publish-results", {"contents": "read", "id-token": "write", "pages": "write"}),
        ("deploy-pages", {"contents": "read", "id-token": "write", "pages": "write"}),
        ("trigger-post-finalization", {"actions": "write", "contents": "read"}),
        ("verify-published-pages", {"contents": "read"}),
    ],
)
def test_each_job_holds_only_the_permissions_it_needs(job: str, expected: dict) -> None:
    assert _jobs()[job]["permissions"] == expected

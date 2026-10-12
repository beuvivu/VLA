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
import shutil
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
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
        (tmp / "src").mkdir()
        (tmp / "src" / "sync.py").write_text(FAKE_SYNC, encoding="utf-8")
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


def test_a_repeated_live_verified_call_after_full_finalization_is_skipped(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    runner.stored(runner.today)
    runner.predicted(runner.today + timedelta(days=1))
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert out["run"] == "false"
    assert out["reason"] == "already-finalized"


@pytest.mark.parametrize("missing", ["loto", "de"])
def test_a_live_verified_call_still_runs_when_the_pipeline_did_not_finish(
    tmp_path: Path, missing: str
) -> None:
    """Kết quả đã chốt nhưng chưa có dự báo kỳ sau (pipeline hỏng giữa chừng): phải chạy lại."""
    runner = Runner(tmp_path)
    runner.stored(runner.today)
    runner.predicted(runner.today + timedelta(days=1), modes=[m for m in ("loto", "de") if m != missing])
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert out["run"] == "true"


def test_a_live_verified_call_for_a_new_draw_runs(tmp_path: Path) -> None:
    """Dự báo cho HÔM NAY có từ tối qua; nó không được làm lượt hôm nay bị bỏ qua."""
    runner = Runner(tmp_path)
    runner.stored(runner.today - timedelta(days=1))
    runner.predicted(runner.today)
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="live_verified")
    assert out["run"] == "true"


def test_a_manual_run_is_never_skipped(tmp_path: Path) -> None:
    """Lượt gọi tay luôn chạy, kể cả khi kỳ mà guard nhắm tới đã hoàn tất trọn vẹn."""
    runner = Runner(tmp_path)
    now = datetime.now(VN)
    # Đúng mốc guard tính cho lượt không phải live_verified: qua 18:35 là hôm nay.
    target = runner.today if now.time() >= time(18, 35) else runner.today - timedelta(days=1)
    runner.stored(target)
    runner.predicted(target + timedelta(days=1))
    out = runner.run("canonical", "guard", event="workflow_dispatch", reason="manual")
    assert out["target"] == target.isoformat()
    assert out["run"] == "true"


# --- Trang kết quả đi trước pipeline -------------------------------------------


def test_the_results_pages_do_not_wait_for_the_analytics_pipeline() -> None:
    jobs = _jobs()
    publish = jobs["publish-results"]
    assert _needs(publish) == {"canonical"}, "chờ job update là chờ ~5 phút pipeline"
    assert _needs(jobs["update"]) == {"canonical"}
    build = "\n".join(step.get("run", "") for step in publish["steps"])
    order = [
        "src/position_bridges.py",
        "src/build_landing_page.py",
        "src/build_fun_prediction.py",
        "src/build_traditional_results.py",
    ]
    positions = [build.index(script) for script in order]
    assert positions == sorted(positions), "cầu vị trí → trang chủ → bảng mô phỏng"
    uses = [step.get("uses", "") for step in publish["steps"]]
    assert any(u.startswith("actions/deploy-pages@") for u in uses)
    assert "git push" not in build, "bản kết quả không commit; pipeline commit bản đầy đủ"


def test_the_full_deploy_comes_after_the_results_deploy() -> None:
    """Hai lượt triển khai trong cùng một lượt chạy: bản đầy đủ phải là bản sau cùng."""
    deploy = _jobs()["deploy-pages"]
    assert _needs(deploy) == {"update", "publish-results"}
    assert "always()" in deploy["if"], "publish-results hỏng không được chặn bản đầy đủ"
    assert "needs.update.result == 'success'" in deploy["if"]


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

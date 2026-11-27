from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
REAL_DATE = shutil.which("date")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or REAL_DATE is None,
    reason="cần bash, git và date",
)


def _step(workflow: str, job: str, key: str) -> dict:
    doc = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8"))
    for step in doc["jobs"][job]["steps"]:
        if key in (step.get("id"), step.get("name")):
            return step
    raise AssertionError(f"{workflow}: không thấy bước {key!r} trong job {job!r}")


def _shell_command(step: dict, script: Path) -> list[str]:
    if step.get("shell") == "bash":
        return ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)]
    return ["bash", "-e", str(script)]


def _write_exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class LiveHarness:

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        _write_exe(self.bin / "date", f'exec {REAL_DATE} -d "@$(cat "$FAKE_DIR/clock")" "$@"\n')
        _write_exe(
            self.bin / "sleep",
            'now=$(cat "$FAKE_DIR/clock")\n'
            'echo $(( now + $1 )) > "$FAKE_DIR/clock"\n'
            'echo "$1" >> "$FAKE_DIR/sleeps"\n',
        )
        _write_exe(
            self.bin / "git",
            'case "$1" in\n'
            "  config) exit 0 ;;\n"
            "  hash-object) echo blob ;;\n"
            '  mktree|commit-tree) cat > /dev/null; echo "obj$RANDOM" ;;\n'
            "  push)\n"
            '    left=$(cat "$FAKE_DIR/push_failures")\n'
            "    if (( left > 0 )); then\n"
            '      echo $(( left - 1 )) > "$FAKE_DIR/push_failures"\n'
            '      echo "remote: Internal Server Error" >&2\n'
            "      exit 1\n"
            "    fi\n"
            '    cat "$FAKE_DIR/clock" >> "$FAKE_DIR/pushes" ;;\n'
            '  *) echo "git giả không hiểu: $*" >&2; exit 2 ;;\n'
            "esac\n",
        )
        _write_exe(
            self.bin / "python",
            'if [[ "$1" == "src/ingest/live_sync.py" ]]; then\n'
            '  status=$(head -n 1 "$FAKE_DIR/statuses")\n'
            '  if (( $(wc -l < "$FAKE_DIR/statuses") > 1 )); then sed -i 1d "$FAKE_DIR/statuses"; fi\n'
            '  printf \'{"status": "%s", "checked_at_utc": "%s"}\' "$status" "$RANDOM" > "$3"\n'
            '  echo "$(cat "$FAKE_DIR/clock") $status" >> "$FAKE_DIR/polls"\n'
            "  exit 0\n"
            "fi\n"
            f'exec {sys.executable} "$@"\n',
        )

    def run(
        self,
        start: datetime,
        *,
        statuses: list[str],
        push_failures: int = 0,
        max_seconds: int = 3600,
    ) -> subprocess.CompletedProcess[str]:
        step = _step("live-results.yml", "live", "poll")
        script = self.tmp / "poll.sh"
        script.write_text(step["run"], encoding="utf-8")
        (self.tmp / "clock").write_text(str(int(start.timestamp())), encoding="utf-8")
        (self.tmp / "statuses").write_text("\n".join(statuses) + "\n", encoding="utf-8")
        (self.tmp / "push_failures").write_text(str(push_failures), encoding="utf-8")
        for name in ("output", "polls", "pushes", "sleeps"):
            (self.tmp / name).write_text("", encoding="utf-8")
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "TZ": "Asia/Ho_Chi_Minh",
            "FAKE_DIR": str(self.tmp),
            "GITHUB_OUTPUT": str(self.tmp / "output"),
            "RUNNER_TEMP": str(self.tmp),
            "POLL_SECONDS": "15",
            "MAX_SECONDS": str(max_seconds),
        }
        return subprocess.run(
            _shell_command(step, script),
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def lines(self, name: str) -> list[str]:
        return (self.tmp / name).read_text(encoding="utf-8").split()

    def output(self) -> str:
        return (self.tmp / "output").read_text(encoding="utf-8")

    def polls(self) -> list[tuple[datetime, str]]:
        rows = (self.tmp / "polls").read_text(encoding="utf-8").splitlines()
        return [
            (datetime.fromtimestamp(int(ts), VN), status)
            for ts, status in (row.split() for row in rows)
        ]


def _vn(hhmmss: str) -> datetime:
    h, m, s = (int(x) for x in (hhmmss + ":00")[:8].split(":"))
    return datetime(2026, 9, 25, h, m, s, tzinfo=VN)


@pytest.fixture
def live(tmp_path: Path) -> LiveHarness:
    return LiveHarness(tmp_path)


@pytest.mark.parametrize(
    "start",
    [
        "17:00:40",
        "17:08:00",
        "17:09:30",
        "18:07:30",
        "18:08:00",
        "18:09:59",
        "18:10:00",
        "19:08:00",
        "14:08:00",
        "16:09:00",
    ],
)
def test_live_poll_starts_polling_at_every_minute_of_the_draw_window(
    live: LiveHarness, start: str
) -> None:
    result = live.run(_vn(start), statuses=["live", "complete_verified"])

    assert result.returncode == 0, result.stderr[-600:]
    polls = live.polls()
    assert polls, "bước thoát mà chưa thăm dò lần nào"
    first = polls[0][0]
    assert (first.hour, first.minute) >= (18, 8), f"thăm dò trước khung quay: {first}"
    assert "verified=true" in live.output()


@pytest.mark.parametrize("start", ["08:08:00", "09:09:00", "09:59:00", "13:37:00", "14:07:00"])
def test_live_poll_leaves_too_early_starts_to_a_later_slot(live: LiveHarness, start: str) -> None:
    result = live.run(_vn(start), statuses=["complete_verified"])

    assert result.returncode == 0, result.stderr[-600:]
    assert live.polls() == []
    assert "verified=false" in live.output()


def test_a_transient_push_error_does_not_end_the_live_window(live: LiveHarness) -> None:
    result = live.run(_vn("18:20"), statuses=["live", "complete_verified"], push_failures=1)

    assert result.returncode == 0, result.stderr[-600:]
    assert [status for _, status in live.polls()] == ["live", "complete_verified"]
    assert len(live.lines("pushes")) == 2, "ảnh chụp đầu phải được đẩy lại, không bị bỏ"
    assert "verified=true" in live.output()


def test_a_verified_result_is_republished_until_the_push_goes_through(
    live: LiveHarness,
) -> None:
    result = live.run(_vn("18:30"), statuses=["complete_verified"], push_failures=4)

    assert result.returncode == 0, result.stderr[-600:]
    assert len(live.polls()) == 2, "vòng đầu hỏng cả ba lần đẩy, vòng hai phải thử tiếp"
    assert len(live.lines("pushes")) == 1
    assert "verified=true" in live.output()


def test_a_push_that_never_recovers_ends_at_the_time_limit_not_a_crash(
    live: LiveHarness,
) -> None:
    result = live.run(
        _vn("18:30"), statuses=["complete_verified"], push_failures=10**6, max_seconds=120
    )

    assert result.returncode == 0, result.stderr[-600:]
    assert live.lines("pushes") == []
    assert "Chưa đẩy được ảnh chụp live" in result.stdout
    assert 1 < len(live.polls()) < 20
    assert "verified=true" in live.output()


def test_the_live_harness_itself_catches_the_octal_bug(live: LiveHarness, tmp_path: Path) -> None:
    script = tmp_path / "old.sh"
    script.write_text(
        "while true; do\n"
        "  now_min=$(( $(date +%H) * 60 + $(date +%M) ))\n"
        "  (( now_min >= 18 * 60 + 8 )) && break\n"
        "  sleep $(( (18 * 60 + 8 - now_min) * 60 ))\n"
        "done\n"
        'echo "ra khỏi vòng, now_min=[$now_min]"\n',
        encoding="utf-8",
    )
    (tmp_path / "clock").write_text(str(int(_vn("17:08:00").timestamp())), encoding="utf-8")
    (tmp_path / "sleeps").write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{live.bin}{os.pathsep}{os.environ['PATH']}",
        "TZ": "Asia/Ho_Chi_Minh",
        "FAKE_DIR": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "value too great for base" in result.stderr
    assert result.returncode == 0
    assert "ra khỏi vòng, now_min=[]" in result.stdout
    assert (tmp_path / "sleeps").read_text(encoding="utf-8") == ""


@pytest.mark.parametrize(("predictor_code", "step_code"), [(0, 0), (3, 0), (1, 1), (2, 2), (124, 124)])
def test_prediction_step_only_skips_the_explicit_unavailable_exit_code(
    tmp_path: Path, predictor_code: int, step_code: int,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "python", f"exit {predictor_code}\n")
    step = _step("daily_prediction.yml", "predict", "predict")
    script = tmp_path / "predict.sh"
    script.write_text(step["run"], encoding="utf-8")
    output = tmp_path / "output"
    result = subprocess.run(
        _shell_command(step, script), cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == step_code, result.stdout + result.stderr
    if predictor_code in (0, 3):
        assert output.read_text(encoding="utf-8") == (
            "generated=true\n" if predictor_code == 0 else "generated=false\n"
        )


class PredictionRepo:

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        _write_exe(
            self.bin / "python",
            'if [[ "$1" == "src/forecast/modeling/run_daily_prediction.py" ]]; then\n'
            '  if [[ "${PREDICTION_EXIT_CODE:-0}" != 0 ]]; then exit "$PREDICTION_EXIT_CODE"; fi\n'
            '  n=$(( $(cat "$FAKE_DIR/stamp") + 1 )); echo "$n" > "$FAKE_DIR/stamp"\n'
            "  shift=$(cat data/shift 2>/dev/null || echo 0)\n"
            '  p=$(awk -v n="$n" -v s="$shift"'
            " 'BEGIN{printf \"%.17g\", 0.23923968902 + n * 1e-11 + s}')\n"
            '  lift=$(awk -v p="$p" \'BEGIN{printf "%.17g", p - 0.23765728565289646}\')\n'
            '  printf \'{"date": "2026-09-25", "generated_at_local": "t%s",'
            ' "generated_at_utc": "t%s", "top": "%s", "p": %s, "lift": %s}\\n\''
            ' "$n" "$n" "$(cat data/marker)" "$p" "$lift"'
            " > data/predictions_today.json\n"
            "  exit 0\n"
            "fi\n"
            f'exec {sys.executable} "$@"\n',
        )
        _write_exe(self.bin / "sleep", "exit 0\n")
        (tmp / "stamp").write_text("0", encoding="utf-8")
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DIR": str(tmp),
            "HOME": str(tmp),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GITHUB_REF_NAME": "main",
        }
        self.remote = tmp / "remote.git"
        self.git(tmp, "init", "--bare", "-b", "main", str(self.remote))
        seed = tmp / "seed"
        self.git(tmp, "clone", str(self.remote), str(seed))
        (seed / "data").mkdir()
        (seed / "data/marker").write_text("m1\n", encoding="utf-8")
        (seed / "data/predictions_today.json").write_text(
            '{"date": "2026-09-25", "generated_at_local": "t0",'
            ' "generated_at_utc": "t0", "top": "m0"}\n',
            encoding="utf-8",
        )
        self.git(seed, "add", ".")
        self.git(seed, "commit", "-m", "gốc")
        self.git(seed, "push", "origin", "main")

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, check=True
        ).stdout

    def runner(self, name: str) -> Path:
        path = self.tmp / name
        self.git(self.tmp, "clone", str(self.remote), str(path))
        subprocess.run(
            ["python", "src/forecast/modeling/run_daily_prediction.py"], cwd=path, env=self.env, check=True
        )
        return path

    def push_from(self, clone: Path, message: str) -> None:
        self.git(clone, "add", ".")
        self.git(clone, "commit", "-m", message)
        self.git(clone, "push", "origin", "main")

    def run_write_step(self, clone: Path) -> subprocess.CompletedProcess[str]:
        step = _step("daily_prediction.yml", "predict", "Ghi kết quả vào kho")
        script = self.tmp / "write.sh"
        script.write_text(step["run"], encoding="utf-8")
        return subprocess.run(
            _shell_command(step, script),
            cwd=clone,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def remote_file(self, path: str) -> str:
        return self.git(self.tmp, "--git-dir", str(self.remote), "show", f"main:{path}")

    def remote_log(self) -> list[str]:
        return self.git(self.tmp, "--git-dir", str(self.remote), "log", "--format=%s").split("\n")


def test_two_runs_predicting_the_same_draw_do_not_wedge_the_retry_loop(tmp_path: Path) -> None:
    repo = PredictionRepo(tmp_path)
    first = repo.runner("first")
    second = repo.runner("second")
    repo.push_from(first, "data: dự đoán cho kỳ 2026-09-25")

    result = repo.run_write_step(second)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert "unmerged" not in result.stderr
    assert json.loads(repo.remote_file("data/predictions_today.json"))["top"] == "m1"


def test_a_prediction_is_rebuilt_on_the_data_it_is_pushed_on_top_of(tmp_path: Path) -> None:
    repo = PredictionRepo(tmp_path)
    runner = repo.runner("runner")
    other = tmp_path / "other"
    repo.git(tmp_path, "clone", str(repo.remote), str(other))
    (other / "data/marker").write_text("m2\n", encoding="utf-8")
    repo.push_from(other, "data: kỳ mới")

    result = repo.run_write_step(runner)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert json.loads(repo.remote_file("data/predictions_today.json"))["top"] == "m2"


@pytest.mark.parametrize(("predictor_code", "step_code"), [(3, 0), (1, 1), (2, 2), (124, 124)])
def test_prediction_retry_only_skips_the_explicit_unavailable_exit_code(
    tmp_path: Path, predictor_code: int, step_code: int,
) -> None:
    repo = PredictionRepo(tmp_path)
    runner = repo.runner("runner")
    other = tmp_path / "other"
    repo.git(tmp_path, "clone", str(repo.remote), str(other))
    (other / "data/marker").write_text("m2\n", encoding="utf-8")
    repo.push_from(other, "data: kỳ mới")
    before = repo.remote_file("data/predictions_today.json")
    repo.env["PREDICTION_EXIT_CODE"] = str(predictor_code)

    result = repo.run_write_step(runner)

    assert result.returncode == step_code, result.stdout + result.stderr
    assert repo.remote_file("data/predictions_today.json") == before


def test_a_timestamp_or_float_noise_change_is_not_committed(tmp_path: Path) -> None:
    repo = PredictionRepo(tmp_path)
    first = repo.runner("first")
    repo.push_from(first, "data: dự đoán cho kỳ 2026-09-25")
    before = repo.remote_log()
    again = repo.runner("again")
    assert repo.remote_file("data/predictions_today.json") != (
        again / "data/predictions_today.json"
    ).read_text(encoding="utf-8"), "mẫu dựng sẵn phải thật sự khác byte"

    result = repo.run_write_step(again)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert repo.remote_log() == before


def test_a_meaningful_probability_change_is_still_committed(tmp_path: Path) -> None:
    repo = PredictionRepo(tmp_path)
    first = repo.runner("first")
    repo.push_from(first, "data: dự đoán cho kỳ 2026-09-25")
    other = tmp_path / "other"
    repo.git(tmp_path, "clone", str(repo.remote), str(other))
    (other / "data/shift").write_text("0.001\n", encoding="utf-8")
    repo.push_from(other, "data: dữ liệu làm xác suất đổi")
    runner = repo.runner("runner")

    result = repo.run_write_step(runner)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    published = json.loads(repo.remote_file("data/predictions_today.json"))
    assert published["p"] == pytest.approx(0.23923968902 + 0.001, abs=1e-6)


def _run_dispatch_step(
    tmp: Path, replies: list[int]
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: list[dict] = []
    queue = list(replies)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(
                {
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(body),
                }
            )
            self.send_response(queue.pop(0) if len(queue) > 1 else queue[0])
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        step = _step("live-results.yml", "live", "Kích hoạt hoàn tất dữ liệu ngày ngay lập tức")
        script = tmp / "dispatch.sh"
        script.write_text(step["run"], encoding="utf-8")
        fake = tmp / "bin"
        fake.mkdir(exist_ok=True)
        _write_exe(fake / "python", f'exec {sys.executable} "$@"\n')
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "GH_TOKEN": "khong-phai-token-that",
            "REPOSITORY": "chu/kho",
            "DEFAULT_BRANCH": "main",
            "GITHUB_API_URL": f"http://127.0.0.1:{server.server_port}",
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
        }
        result = subprocess.run(
            _shell_command(step, script),
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        server.shutdown()
    return result, seen


def test_the_finalization_dispatch_retries_a_transient_server_error(tmp_path: Path) -> None:
    result, seen = _run_dispatch_step(tmp_path, [502, 204])

    assert result.returncode == 0, result.stderr[-600:]
    assert len(seen) == 2
    assert seen[-1]["path"] == "/repos/chu/kho/actions/workflows/update-data.yml/dispatches"
    assert seen[-1]["body"] == {"ref": "main", "inputs": {"reason": "live_verified"}}
    assert seen[-1]["auth"] == "Bearer khong-phai-token-that"


def test_the_finalization_dispatch_does_not_retry_a_permission_error(tmp_path: Path) -> None:
    result, seen = _run_dispatch_step(tmp_path, [403])

    assert result.returncode != 0
    assert len(seen) == 1


def _run_live_reconcile_push(tmp_path: Path, failures: int) -> tuple[subprocess.CompletedProcess, int]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "push_failures").write_text(str(failures), encoding="utf-8")
    (tmp_path / "pushes").write_text("", encoding="utf-8")
    _write_exe(bin_dir / "sleep", "exit 0\n")
    _write_exe(
        bin_dir / "git",
        'case "$1" in\n'
        "  config) exit 0 ;;\n"
        '  hash-object) [[ -f "$3" ]] || exit 9; echo blob ;;\n'
        '  mktree|commit-tree) cat > /dev/null; echo "obj$RANDOM" ;;\n'
        "  push)\n"
        '    left=$(cat "$FAKE_DIR/push_failures")\n'
        "    if (( left > 0 )); then\n"
        '      echo $(( left - 1 )) > "$FAKE_DIR/push_failures"\n'
        "      echo \"! [remote rejected] obj -> live (cannot lock ref 'refs/heads/live')\" >&2\n"
        "      exit 1\n"
        "    fi\n"
        '    echo "$3" >> "$FAKE_DIR/pushes" ;;\n'
        '  *) echo "git giả không hiểu: $*" >&2; exit 2 ;;\n'
        "esac\n",
    )
    step = _step("post-finalization.yml", "reconcile", "Xuất bản ảnh chụp chuẩn lên nhánh live")
    assert step["env"] == {"LIVE_PATH": "${{ steps.live-payload.outputs.path }}"}
    live_json = tmp_path / "live-canonical.json"
    live_json.write_text('{"status": "complete_verified"}', encoding="utf-8")
    script = tmp_path / "publish.sh"
    script.write_text(step["run"], encoding="utf-8")
    result = subprocess.run(
        _shell_command(step, script),
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "FAKE_DIR": str(tmp_path), "LIVE_PATH": str(live_json)},
        capture_output=True, text=True, timeout=60, check=False,
    )
    pushes = len((tmp_path / "pushes").read_text(encoding="utf-8").splitlines())
    return result, pushes


def test_a_concurrent_live_push_does_not_fail_the_canonical_reconcile(tmp_path: Path) -> None:
    result, pushes = _run_live_reconcile_push(tmp_path, failures=1)

    assert result.returncode == 0, result.stderr[-600:]
    assert pushes == 1


def test_a_live_push_that_never_recovers_fails_the_reconcile(tmp_path: Path) -> None:
    result, pushes = _run_live_reconcile_push(tmp_path, failures=10**6)

    assert result.returncode != 0
    assert pushes == 0
    assert "Không đẩy được ảnh chụp chuẩn" in result.stdout


def _git_in(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_the_page_build_keeps_every_tracked_forecast_file_the_cache_overwrote(tmp_path: Path) -> None:
    doc = yaml.safe_load((ROOT / ".github/workflows/vietlott-results.yml").read_text(encoding="utf-8"))
    steps = doc["jobs"]["build"]["steps"]
    cache = next(s for s in steps if str(s.get("uses", "")).startswith("actions/cache/restore"))
    keep = _step("vietlott-results.yml", "build", "Giữ bản tóm tắt mô hình đã commit")
    assert steps.index(cache) < steps.index(keep), "phải giữ bản đã commit SAU khi khôi phục cache"
    assert "vietlott/data/forecast/*.json" in cache["with"]["path"]

    repo = tmp_path / "repo"
    forecast = repo / "vietlott" / "data" / "forecast"
    forecast.mkdir(parents=True)
    tracked = {"multi-agent-summary.json": '{"v": 2}', "transfer.json": '{"engine_fingerprint": "moi"}',
               "tep-moi-sau-nay.json": '{"a": 1}'}
    for name, text in tracked.items():
        (forecast / name).write_text(text, encoding="utf-8")
    _git_in(repo, "init", "-q")
    _git_in(repo, "add", ".")
    _git_in(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "goc")
    for name in tracked:
        (forecast / name).write_text('{"cu": true}', encoding="utf-8")
    (forecast / "state-mega645.json").write_text('{"trang_thai": 1}', encoding="utf-8")

    script = tmp_path / "keep.sh"
    script.write_text(keep["run"], encoding="utf-8")
    result = subprocess.run(_shell_command(keep, script), cwd=repo, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    for name, text in tracked.items():
        assert (forecast / name).read_text(encoding="utf-8") == text, name
    assert (forecast / "state-mega645.json").read_text(encoding="utf-8") == '{"trang_thai": 1}'
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True)
    assert status.stdout.split() == ["??", "vietlott/data/forecast/state-mega645.json"]

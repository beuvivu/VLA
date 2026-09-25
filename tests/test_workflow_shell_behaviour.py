"""Chạy THẬT các khối shell của workflow, thay vì đọc chúng như chuỗi.

Vì sao cần
==========

`tests/test_workflows.py` soi văn bản workflow: có mốc cron này, có biến
kia. Cách đó không thấy được ba lỗi đã làm hỏng việc thật trên kho này, vì cả
ba đều là lỗi HÀNH VI của vài dòng bash:

* ``live-results.yml`` tính phút trong ngày bằng
  ``$(( $(date +%H) * 60 + $(date +%M) ))``. Bash đọc "08" và "09" là hệ bát
  phân; bash 5.2 khi ấy bỏ ngang cả vòng chờ mà ``set -e`` không bắt được.
  Lượt nổ lúc 17:08 thăm dò ngay giờ trống 17:08–18:08 rồi hết giờ đúng lúc
  kỳ quay bắt đầu; lượt nổ trong giờ 08, 09 thăm dò khi chẳng có gì để thăm.
* Cũng bước ấy: lượt #164 chết vì GitHub trả HTTP 500 MỘT lần khi đẩy ảnh
  chụp. Với ``set -e``, một lỗi thoáng qua giết cả vòng thăm dò 60 phút.
* ``daily_prediction.yml``, lượt 36037174777: rebase xung đột để cây ở giữa
  chừng, ba lần thử lại sau đều chết vì "unmerged files".

Mỗi phép kiểm dưới đây lấy nguyên khối ``run:`` từ YAML và chạy nó bằng đúng
lệnh shell GitHub dùng. Chỉ những thứ chạm ra ngoài bị thay: đồng hồ, lệnh
ngủ, nguồn dữ liệu, và (cho bước live) lệnh đẩy. Bước ghi dự đoán thì chạy
git THẬT trên một kho trần cục bộ, vì lỗi của nó nằm chính ở trạng thái git.
"""

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

ROOT = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
REAL_DATE = shutil.which("date")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or REAL_DATE is None,
    reason="cần bash, git và date",
)


def _step(workflow: str, job: str, key: str) -> dict:
    """Bước có ``id`` hoặc ``name`` là ``key`` trong ``job``."""
    doc = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8"))
    for step in doc["jobs"][job]["steps"]:
        if key in (step.get("id"), step.get("name")):
            return step
    raise AssertionError(f"{workflow}: không thấy bước {key!r} trong job {job!r}")


def _shell_command(step: dict, script: Path) -> list[str]:
    """Đúng lệnh GitHub dùng để chạy một khối ``run:`` trên ubuntu-latest."""
    if step.get("shell") == "bash":
        return ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)]
    return ["bash", "-e", str(script)]


def _write_exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# ---------------------------------------------------------------------------
# live-results.yml — bước "poll"
# ---------------------------------------------------------------------------


class LiveHarness:
    """Chạy bước thăm dò với đồng hồ giả, nguồn giả và lệnh đẩy giả.

    ``sleep`` giả không ngủ mà đẩy đồng hồ giả tới trước, nên một lượt chờ 68
    phút chạy trong vài phần mười giây mà vẫn đi qua đúng các phút thật.
    """

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
            'if [[ "$1" == "src/live_sync.py" ]]; then\n'
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
            check=False,  # phép kiểm tự khẳng định mã thoát
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
    # 17:08 và 17:09:30 là hai phút bát phân TRƯỚC khung: dòng cũ bỏ qua bước
    # chờ và thăm dò ngay giờ trống. 17:00:40 ngủ 68 phút rồi thức ở phút bát
    # phân 18:08; 18:10 là mốc bộ hẹn giờ ngoài được hướng dẫn dùng.
    [
        "17:00:40",
        "17:08:00",
        "17:09:30",
        "18:07:30",
        "18:08:00",
        "18:09:59",
        "18:10:00",
        "19:08:00",
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


@pytest.mark.parametrize("start", ["08:08:00", "09:09:00", "09:59:00", "13:37:00", "16:09:00"])
def test_live_poll_leaves_too_early_starts_to_a_later_slot(live: LiveHarness, start: str) -> None:
    """Giờ 08, 09 và phút 08, 09 là số bát phân: trước đây lượt nổ lúc ấy bỏ
    qua trần chờ và thăm dò 60 phút giữa giờ trống, thay vì thoát sạch để mốc
    sau xử lý."""
    result = live.run(_vn(start), statuses=["complete_verified"])

    assert result.returncode == 0, result.stderr[-600:]
    assert live.polls() == []
    assert "verified=false" in live.output()


def test_a_transient_push_error_does_not_end_the_live_window(live: LiveHarness) -> None:
    """Lượt #164: một lần HTTP 500 khi đẩy từng giết cả vòng thăm dò."""
    result = live.run(_vn("18:20"), statuses=["live", "complete_verified"], push_failures=1)

    assert result.returncode == 0, result.stderr[-600:]
    assert [status for _, status in live.polls()] == ["live", "complete_verified"]
    assert len(live.lines("pushes")) == 2, "ảnh chụp đầu phải được đẩy lại, không bị bỏ"
    assert "verified=true" in live.output()


def test_a_verified_result_is_republished_until_the_push_goes_through(
    live: LiveHarness,
) -> None:
    """Đẩy hỏng hết lượt thử của một vòng thì vòng SAU phải đẩy lại, và chỉ
    dừng khi chính ảnh chụp đã xác minh lên được nhánh live."""
    result = live.run(_vn("18:30"), statuses=["complete_verified"], push_failures=4)

    assert result.returncode == 0, result.stderr[-600:]
    assert len(live.polls()) == 2, "vòng đầu hỏng cả ba lần đẩy, vòng hai phải thử tiếp"
    assert len(live.lines("pushes")) == 1
    assert "verified=true" in live.output()


def test_a_push_that_never_recovers_ends_at_the_time_limit_not_a_crash(
    live: LiveHarness,
) -> None:
    """Hỏng dai dẳng thì hết giờ và báo, không chết giữa chừng, không lặp mãi.

    Và VẪN phát ``verified=true``: cờ ấy kích hoạt hoàn tất dữ liệu ngày, và
    chuỗi update-data → post-finalization ghi ảnh chụp chuẩn lên nhánh live
    từ ``data/xsmb.csv`` — đường sửa duy nhất cho nhánh live khi đẩy từ đây
    hỏng dai dẳng. Giữ cờ lại thì nhánh live kẹt ở ảnh chụp dở tới cron kế.
    """
    result = live.run(
        _vn("18:30"), statuses=["complete_verified"], push_failures=10**6, max_seconds=120
    )

    assert result.returncode == 0, result.stderr[-600:]
    assert live.lines("pushes") == []
    assert "Chưa đẩy được ảnh chụp live" in result.stdout
    assert 1 < len(live.polls()) < 20
    assert "verified=true" in live.output()


def test_the_live_harness_itself_catches_the_octal_bug(live: LiveHarness, tmp_path: Path) -> None:
    """Ghim chính LUẬT trên mẫu dựng sẵn: vòng chờ cũ, chạy qua đúng khung
    này lúc 17:08, phải vấp lỗi bát phân và rơi ra khỏi vòng mà không ngủ.
    Nếu khung giả hỏng (``date`` giả không được dùng, đồng hồ không đi) thì
    các phép kiểm trên xanh vô nghĩa — phép này đỏ."""
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
    # Đúng cơ chế đã đo: set -e KHÔNG dừng bước, vòng bị bỏ ngang, không ngủ.
    assert result.returncode == 0
    assert "ra khỏi vòng, now_min=[]" in result.stdout
    assert (tmp_path / "sleeps").read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# daily_prediction.yml — bước "Ghi kết quả vào kho"
# ---------------------------------------------------------------------------


class PredictionRepo:
    """Kho trần cục bộ đóng vai GitHub, cộng hai bản sao đóng vai hai runner.

    Bộ sinh dự đoán giả ghi ``top`` bằng nội dung ``data/marker`` — tức dự
    đoán là hàm của dữ liệu trên nhánh, đúng như bộ thật — và mỗi lần chạy
    một dấu thời gian mới.
    """

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        _write_exe(
            self.bin / "python",
            'if [[ "$1" == "src/run_daily_prediction.py" ]]; then\n'
            '  n=$(( $(cat "$FAKE_DIR/stamp") + 1 )); echo "$n" > "$FAKE_DIR/stamp"\n'
            '  printf \'{"date": "2026-09-25", "generated_at_local": "t%s",'
            ' "generated_at_utc": "t%s", "top": "%s"}\\n\' "$n" "$n" "$(cat data/marker)"'
            " > data/predictions_today.json\n"
            "  exit 0\n"
            "fi\n"
            f'exec {sys.executable} "$@"\n',
        )
        # Lệnh ngủ giữa các lần thử không có gì để kiểm; bỏ qua cho nhanh.
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
        # Nhánh chính có dữ liệu m1 nhưng dự đoán còn dựng trên m0: kỳ mới
        # vừa về, dự đoán chưa sinh lại.
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
        """Một runner: lấy nhánh chính rồi chạy bước "Sinh dự đoán"."""
        path = self.tmp / name
        self.git(self.tmp, "clone", str(self.remote), str(path))
        subprocess.run(
            ["python", "src/run_daily_prediction.py"], cwd=path, env=self.env, check=True
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
            check=False,  # phép kiểm tự khẳng định mã thoát
        )

    def remote_file(self, path: str) -> str:
        return self.git(self.tmp, "--git-dir", str(self.remote), "show", f"main:{path}")

    def remote_log(self) -> list[str]:
        return self.git(self.tmp, "--git-dir", str(self.remote), "log", "--format=%s").split("\n")


def test_two_runs_predicting_the_same_draw_do_not_wedge_the_retry_loop(tmp_path: Path) -> None:
    """Tái hiện lượt 36037174777: hai runner cùng sinh dự đoán cho một kỳ, một
    runner đẩy trước. Runner sau phải kết thúc XANH, không kẹt giữa rebase."""
    repo = PredictionRepo(tmp_path)
    first = repo.runner("first")
    second = repo.runner("second")
    repo.push_from(first, "data: dự đoán cho kỳ 2026-09-25")

    result = repo.run_write_step(second)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert "unmerged" not in result.stderr
    assert json.loads(repo.remote_file("data/predictions_today.json"))["top"] == "m1"


def test_a_prediction_is_rebuilt_on_the_data_it_is_pushed_on_top_of(tmp_path: Path) -> None:
    """Nhánh chính tiến lên với dữ liệu mới trong lúc runner đang chạy. Dự đoán
    lên kho phải dựng trên dữ liệu MỚI ấy — không phải bản dựng trên dữ liệu
    cũ được rebase lên trên nó, thứ mà `pull --rebase` cũ vui vẻ đẩy lên."""
    repo = PredictionRepo(tmp_path)
    runner = repo.runner("runner")
    other = tmp_path / "other"
    repo.git(tmp_path, "clone", str(repo.remote), str(other))
    (other / "data/marker").write_text("m2\n", encoding="utf-8")
    repo.push_from(other, "data: kỳ mới")

    result = repo.run_write_step(runner)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert json.loads(repo.remote_file("data/predictions_today.json"))["top"] == "m2"


def test_a_timestamp_only_change_is_not_committed(tmp_path: Path) -> None:
    """Tám commit cho cùng một kỳ trong một đêm, chỉ khác dấu thời gian."""
    repo = PredictionRepo(tmp_path)
    first = repo.runner("first")
    repo.push_from(first, "data: dự đoán cho kỳ 2026-09-25")
    before = repo.remote_log()
    again = repo.runner("again")

    result = repo.run_write_step(again)

    assert result.returncode == 0, (result.stdout + result.stderr)[-800:]
    assert repo.remote_log() == before


# ---------------------------------------------------------------------------
# live-results.yml — bước kích hoạt hoàn tất dữ liệu ngày
# ---------------------------------------------------------------------------


def _run_dispatch_step(
    tmp: Path, replies: list[int]
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    """Chạy bước dispatch với một máy chủ cục bộ đóng vai API GitHub."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: list[dict] = []
    queue = list(replies)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — tên do http.server đặt
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
            check=False,  # phép kiểm tự khẳng định mã thoát
        )
    finally:
        server.shutdown()
    return result, seen


def test_the_finalization_dispatch_retries_a_transient_server_error(tmp_path: Path) -> None:
    """Lỗi 5xx một lần không được làm dữ liệu ngày phải chờ tới cron kế tiếp."""
    result, seen = _run_dispatch_step(tmp_path, [502, 204])

    assert result.returncode == 0, result.stderr[-600:]
    assert len(seen) == 2
    assert seen[-1]["path"] == "/repos/chu/kho/actions/workflows/update-data.yml/dispatches"
    assert seen[-1]["body"] == {"ref": "main", "inputs": {"reason": "live_verified"}}
    assert seen[-1]["auth"] == "Bearer khong-phai-token-that"


def test_the_finalization_dispatch_does_not_retry_a_permission_error(tmp_path: Path) -> None:
    """403 là quyền hoặc cấu hình sai: thử lại chỉ che nó đi. Phải đỏ ngay."""
    result, seen = _run_dispatch_step(tmp_path, [403])

    assert result.returncode != 0
    assert len(seen) == 1

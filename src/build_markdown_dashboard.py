from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "DASHBOARD.md"

PRIZE_GROUPS: list[tuple[str, str, list[str], int]] = [
    ("Đặc biệt", "ĐB", ["special"], 5),
    ("Giải nhất", "G1", ["prize1"], 5),
    ("Giải nhì", "G2", ["prize2_1", "prize2_2"], 5),
    ("Giải ba", "G3", [f"prize3_{i}" for i in range(1, 7)], 5),
    ("Giải tư", "G4", [f"prize4_{i}" for i in range(1, 5)], 4),
    ("Giải năm", "G5", [f"prize5_{i}" for i in range(1, 7)], 4),
    ("Giải sáu", "G6", [f"prize6_{i}" for i in range(1, 4)], 3),
    ("Giải bảy", "G7", [f"prize7_{i}" for i in range(1, 5)], 2),
]

FRIENDLY = {
    "advanced": "Advanced statistics",
    "ai_ml": "AI / ML signals",
    "cycle": "Cycle analysis",
    "descriptive_ext": "Descriptive extensions",
    "ensemble": "Ensemble / calibration",
    "excel": "Excel exports",
    "hazard": "Hazard / overdue analysis",
    "history": "Prediction history",
    "markov": "Markov models",
    "ml": "Machine-learning outputs",
    "number_dynamics": "Number dynamics",
    "pairs": "Pair statistics",
    "path_ui": "Path / cầu evidence",
    "predict": "Forecasts & prediction files",
    "prob_eval": "Probability evaluation",
    "research": "Research / falsification lab",
    "significance": "Statistical significance",
    "statistical_signal": "Statistical signals",
}

PREVIEW_PRIORITY = (
    "summary",
    "current",
    "latest",
    "diagnostic",
    "signal",
    "top",
    "quality",
    "weights",
    "calibration",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {"data": obj}
    except Exception:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_Chưa có dữ liệu._"
    head = "| " + " | ".join(_cell(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _fmt_code(value: Any, width: int) -> str:
    try:
        return f"{int(float(str(value))):0{width}d}"
    except Exception:
        text = str(value or "").strip()
        return text.zfill(width) if text else "—"


def _group_value(row: dict[str, str], cols: list[str], width: int) -> str:
    return " · ".join(_fmt_code(row.get(c), width) for c in cols)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _file_link(path: Path, label: str | None = None) -> str:
    rel = _rel(path)
    return f"[{label or path.name}]({rel})"


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _prediction_rows(mode: str, target_date: str, limit: int = 10) -> tuple[Path | None, list[list[Any]]]:
    pred_dir = DATA / "predict"
    preferred = pred_dir / f"predict_next_{mode}_all_{target_date}.csv" if target_date else None
    path: Path | None = preferred if preferred and preferred.exists() else None
    if path is None:
        files = sorted(pred_dir.glob(f"predict_next_{mode}_all_*.csv"))
        path = files[-1] if files else None
    if path is None:
        return None, []

    rows = _read_csv(path)
    out: list[list[Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        num = row.get("number_str") or row.get("number") or ""
        num = _fmt_code(num, 2)
        try:
            prob = f"{float(row.get('prob', 0)) * 100:.3f}%"
        except Exception:
            prob = row.get("prob", "")
        try:
            disagreement = f"{float(row.get('component_disagreement', 0)):.4f}"
        except Exception:
            disagreement = row.get("component_disagreement", "")
        out.append(
            [
                i,
                f"**{num}**" if i <= 4 else num,
                prob,
                row.get("agreement_tier", "—"),
                disagreement or "—",
                "✅" if str(row.get("meta_active", "")).lower() == "true" else "—",
            ]
        )
    return path, out


def _preview_csv(path: Path, max_rows: int = 8, max_cols: int = 7) -> str:
    rows = _read_csv(path)
    if not rows:
        return "_Không đọc được preview hoặc file rỗng._"
    cols = list(rows[0].keys())[:max_cols]
    data = [[r.get(c, "") for c in cols] for r in rows[:max_rows]]
    note = ""
    if len(rows) > max_rows or len(rows[0]) > max_cols:
        note = f"\n\n> Preview {min(len(rows), max_rows)} dòng × {len(cols)} cột; xem file đầy đủ qua liên kết ở trên."
    return _md_table(cols, data) + note


def _preview_json(path: Path) -> str:
    obj = _read_json(path)
    if not obj:
        return "_Không đọc được preview hoặc file rỗng._"
    rows: list[list[Any]] = []
    for key, value in list(obj.items())[:12]:
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if len(text) > 150:
                text = text[:147] + "..."
        else:
            text = value
        rows.append([key, text])
    return _md_table(["Field", "Value"], rows)


def _choose_previews(files: list[Path], limit: int = 2) -> list[Path]:
    candidates = [p for p in files if p.suffix.lower() in {".csv", ".json"} and p.stat().st_size <= 750_000]
    candidates.sort(
        key=lambda p: (
            min((i for i, token in enumerate(PREVIEW_PRIORITY) if token in p.name.lower()), default=999),
            p.name.lower(),
        )
    )
    return candidates[:limit]


def _daily_sections(results: list[dict[str, str]]) -> str:
    if not results:
        return "_Chưa có canonical daily result._"

    latest = results[-1]
    latest_rows = []
    for long_name, short_name, cols, width in PRIZE_GROUPS:
        value = _group_value(latest, cols, width)
        if short_name == "ĐB":
            value = f"**{value}**"
        latest_rows.append([long_name, value])

    recent_rows: list[list[Any]] = []
    for row in reversed(results[-10:]):
        recent_rows.append(
            [
                row.get("date", ""),
                f"**{_group_value(row, ['special'], 5)}**",
                _group_value(row, ["prize1"], 5),
                _group_value(row, ["prize2_1", "prize2_2"], 5),
                _group_value(row, [f"prize7_{i}" for i in range(1, 5)], 2),
            ]
        )

    history_rows: list[list[Any]] = []
    for row in reversed(results):
        history_rows.append(
            [
                row.get("date", ""),
                _group_value(row, ["special"], 5),
                _group_value(row, ["prize1"], 5),
                _group_value(row, ["prize2_1", "prize2_2"], 5),
                _group_value(row, [f"prize3_{i}" for i in range(1, 7)], 5),
                _group_value(row, [f"prize4_{i}" for i in range(1, 5)], 4),
                _group_value(row, [f"prize5_{i}" for i in range(1, 7)], 4),
                _group_value(row, [f"prize6_{i}" for i in range(1, 4)], 3),
                _group_value(row, [f"prize7_{i}" for i in range(1, 5)], 2),
            ]
        )

    return f"""
### 🏆 Kết quả mới nhất — {latest.get('date', '')}

{_md_table(['Giải', 'Kết quả'], latest_rows)}

### 📅 10 kỳ gần nhất

{_md_table(['Ngày', 'ĐB', 'G1', 'G2', 'G7'], recent_rows)}

<details>
<summary><strong>🗂️ Toàn bộ lịch sử daily — {len(results)} kỳ</strong></summary>

> Bảng dưới đây chứa toàn bộ canonical daily results hiện có trong `data/xsmb.csv`, trình bày đủ GĐB → G7. Mới nhất nằm trên cùng.

{_md_table(['Ngày', 'ĐB', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7'], history_rows)}

</details>
""".strip()


def _catalog() -> str:
    all_files = sorted(p for p in DATA.rglob("*") if p.is_file())
    root_files = [p for p in all_files if p.parent == DATA]
    groups: dict[str, list[Path]] = {}
    for path in all_files:
        rel = path.relative_to(DATA)
        if len(rel.parts) <= 1:
            continue
        groups.setdefault(rel.parts[0], []).append(path)

    chunks: list[str] = []
    if root_files:
        rows = [[_file_link(p), p.suffix.lower().lstrip(".") or "file", _human_size(p.stat().st_size)] for p in root_files]
        chunks.append("### 📦 Root data files\n\n" + _md_table(["File", "Type", "Size"], rows))

    ordered = sorted(groups, key=lambda key: (list(FRIENDLY).index(key) if key in FRIENDLY else 999, key))
    for group in ordered:
        files = groups[group]
        label = FRIENDLY.get(group, group.replace("_", " ").title())
        rows = [
            [
                _file_link(p, p.relative_to(DATA / group).as_posix()),
                p.suffix.lower().lstrip(".") or "file",
                _human_size(p.stat().st_size),
            ]
            for p in files
        ]
        block = [
            "<details>",
            f"<summary><strong>📁 {label}</strong> · {len(files)} files</summary>",
            "",
            _md_table(["File", "Type", "Size"], rows),
        ]
        previews = _choose_previews(files)
        if previews:
            block.extend(["", "#### Quick preview"])
            for p in previews:
                block.extend(["", f"**{_file_link(p)}**", ""])
                block.append(_preview_csv(p) if p.suffix.lower() == ".csv" else _preview_json(p))
        block.extend(["", "</details>"])
        chunks.append("\n".join(block))

    return "\n\n".join(chunks)


def main() -> None:
    health = _read_json(DATA / "health.json")
    loto = _read_json(DATA / "predict" / "picks_loto.json")
    de = _read_json(DATA / "predict" / "picks_de.json")
    results = _read_csv(DATA / "xsmb.csv")

    latest_date = str(health.get("latest_date") or (results[-1].get("date") if results else "—"))
    target_date = str(loto.get("target_date") or de.get("target_date") or "—")
    row_count = int(health.get("row_count") or len(results))
    missing_count = int(health.get("missing_count") or 0)
    generated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    loto_path, loto_rows = _prediction_rows("loto", str(loto.get("target_date") or ""))
    de_path, de_rows = _prediction_rows("de", str(de.get("target_date") or ""))

    loto_top10 = " · ".join(f"`{x}`" for x in loto.get("top10", [])) or "—"
    de_top10 = " · ".join(f"`{x}`" for x in de.get("top10", [])) or "—"
    loto_meta = loto.get("meta", {}) if isinstance(loto.get("meta"), dict) else {}
    de_meta = de.get("meta", {}) if isinstance(de.get("meta"), dict) else {}

    total_files = sum(1 for p in DATA.rglob("*") if p.is_file())
    total_dirs = sum(1 for p in DATA.iterdir() if p.is_dir()) if DATA.exists() else 0

    status_badge = "HEALTHY-cfe8dc" if health.get("ok") else "CHECK-f6d6d6"
    loto_badge = "ACTIVE-d9ead3" if loto_meta.get("active") else "BASELINE-e8e8e8"
    de_badge = "ACTIVE-d9ead3" if de_meta.get("active") else "VALIDATION__GATED-f4cccc"

    dashboard = f"""<div align="center">

# 🎯 VLA · XSMB Analytics Dashboard

**Daily Results · Forecast · AI/ML · Statistical Evidence · Research Lab · Data Catalog**

![Data Health](https://img.shields.io/badge/Data-{status_badge}?style=flat-square)
![Latest](https://img.shields.io/badge/Latest-{latest_date.replace('-', '--')}-d9eaf7?style=flat-square)
![Forecast](https://img.shields.io/badge/Forecast-{target_date.replace('-', '--')}-eadcf8?style=flat-square)
![Loto Meta](https://img.shields.io/badge/Loto_Meta-{loto_badge}?style=flat-square)
![De Meta](https://img.shields.io/badge/De_Meta-{de_badge}?style=flat-square)

<sub>Auto-generated by `src/build_markdown_dashboard.py` · Generated {generated}</sub>

</div>

> [!NOTE]
> Đây là **analytics/research dashboard**, không phải cam kết kết quả. Xác suất và tín hiệu được trình bày kèm validation state để phân biệt production evidence với research-only patterns.

## 🧭 Navigation

[Daily Results](#-daily-results) · [Forecast](#-forecast--prediction) · [Model & Evidence](#-model--evidence) · [Statistics](#-statistical-data-center) · [Data Catalog](#-complete-data-catalog) · [System Health](#-system-health)

---

## 🟢 Executive Snapshot

| Metric | Current state |
| --- | --- |
| Canonical latest | **{latest_date}** |
| Forecast target | **{target_date}** |
| Canonical rows | **{row_count:,}** |
| Missing dates | **{missing_count}** |
| Data files indexed | **{total_files:,}** across **{total_dirs}** top-level folders |
| Lô tô stacked challenger | **{'ACTIVE' if loto_meta.get('active') else 'INACTIVE'}** · trust `{loto_meta.get('trust', 0)}` · quality pass `{loto_meta.get('quality_pass', False)}` |
| Đề stacked challenger | **{'ACTIVE' if de_meta.get('active') else 'INACTIVE'}** · trust `{de_meta.get('trust', 0)}` · quality pass `{de_meta.get('quality_pass', False)}` |

---

## 🎟️ Daily Results

{_daily_sections(results)}

**Canonical sources:** {_file_link(DATA / 'xsmb.csv')} · {_file_link(DATA / 'xsmb.json')} · {_file_link(DATA / 'xsmb-2-digits.csv')} · {_file_link(DATA / 'xsmb-sparse.csv')}

---

## 🔮 Forecast & Prediction

### Lô tô · target {loto.get('target_date', '—')}

**Top 10:** {loto_top10}

{_md_table(['#', 'Number', 'Probability', 'Agreement', 'Disagreement', 'Meta'], loto_rows)}

Source: {_file_link(DATA / 'predict' / 'picks_loto.json')}""" + (f" · {_file_link(loto_path)}" if loto_path else "") + f"""

<details>
<summary><strong>Model state · Lô tô</strong></summary>

{_md_table(['Field', 'Value'], [
    ['Anchor date', loto.get('anchor_date', '—')],
    ['Target date', loto.get('target_date', '—')],
    ['Meta active', loto_meta.get('active', False)],
    ['Meta trust', loto_meta.get('trust', 0)],
    ['Quality pass', loto_meta.get('quality_pass', False)],
    ['Reason', loto_meta.get('reason', '—')],
    ['Candidate', loto_meta.get('candidate', '—')],
    ['Validation LogLoss', loto_meta.get('validation_logloss', '—')],
    ['Baseline LogLoss', loto_meta.get('baseline_validation_logloss', '—')],
    ['LogLoss skill', loto_meta.get('logloss_skill', '—')],
    ['Brier skill', loto_meta.get('brier_skill', '—')],
])}

</details>

### Đề / ĐB · target {de.get('target_date', '—')}

**Top 10:** {de_top10}

{_md_table(['#', 'Number', 'Probability', 'Agreement', 'Disagreement', 'Meta'], de_rows)}

Source: {_file_link(DATA / 'predict' / 'picks_de.json')}""" + (f" · {_file_link(de_path)}" if de_path else "") + f"""

<details>
<summary><strong>Model state · Đề</strong></summary>

{_md_table(['Field', 'Value'], [
    ['Anchor date', de.get('anchor_date', '—')],
    ['Target date', de.get('target_date', '—')],
    ['Meta active', de_meta.get('active', False)],
    ['Meta trust', de_meta.get('trust', 0)],
    ['Quality pass', de_meta.get('quality_pass', False)],
    ['Reason', de_meta.get('reason', '—')],
    ['Validation LogLoss', de_meta.get('validation_logloss', '—')],
    ['Baseline LogLoss', de_meta.get('baseline_validation_logloss', '—')],
    ['LogLoss skill', de_meta.get('logloss_skill', '—')],
])}

</details>

### Component weights

{_md_table(['Component', 'Lô tô', 'Đề'], [
    ['Base ML', loto.get('weights', {}).get('w_ml', '—'), de.get('weights', {}).get('w_ml', '—')],
    ['Cầu / kèo ML', loto.get('weights', {}).get('w_cau', '—'), de.get('weights', {}).get('w_cau', '—')],
    ['Statistical signal', loto.get('weights', {}).get('w_stat', '—'), de.get('weights', {}).get('w_stat', '—')],
    ['Active paths', loto.get('weights', {}).get('w_active', '—'), de.get('weights', {}).get('w_active', '—')],
    ['Stable paths', loto.get('weights', {}).get('w_stable', '—'), de.get('weights', {}).get('w_stable', '—')],
])}

---

## 🧠 Model & Evidence

| Layer | Purpose | Data |
| --- | --- | --- |
| Base ML | Production probability model | [data/ml](data/ml/) |
| Cầu / kèo ML | Pattern-aware learned signal | [data/ai_ml](data/ai_ml/) |
| Statistical signal | Frequency / recurrence / evidence aggregation | [data/statistical_signal](data/statistical_signal/) |
| Active / stable paths | Path / positional evidence | [data/path_ui](data/path_ui/) |
| Ensemble | Learned weights + calibration | [data/ensemble](data/ensemble/) |
| Probability evaluation | OOS LogLoss / Brier history | [data/prob_eval](data/prob_eval/) |
| Significance | Statistical testing / diagnostics | [data/significance](data/significance/) |
| Research firewall | Falsification, FDR, reality checks | [data/research](data/research/) |

---

## 📊 Statistical Data Center

Các nhóm dưới đây là **toàn bộ lớp thống kê hiện có trong `data/`**. Mỗi nhóm có liên kết thư mục nguồn; phần Complete Data Catalog bên dưới tự động liệt kê **mọi file**, nên khi pipeline sinh thêm artifact mới, dashboard cũng tự nhận biết ở lần chạy kế tiếp.

| Domain | Folder | Typical use |
| --- | --- | --- |
| Advanced | [advanced](data/advanced/) | Conditional, rhythm, overdue, head/tail/total, cycles |
| Descriptive | [descriptive_ext](data/descriptive_ext/) | Recency, gap, head table, tổng/chạm descriptive |
| Cycle | [cycle](data/cycle/) | Chu kỳ xuất hiện |
| Hazard | [hazard](data/hazard/) | Hazard / overdue probability |
| Markov | [markov](data/markov/) | Transition dependence |
| Number dynamics | [number_dynamics](data/number_dynamics/) | Hot/cold/gan/recency dynamics |
| Pairs | [pairs](data/pairs/) | Pair/co-occurrence statistics |
| Significance | [significance](data/significance/) | p/q-values and global diagnostics |
| Statistical signals | [statistical_signal](data/statistical_signal/) | Production statistical probability inputs |
| Paths | [path_ui](data/path_ui/) | Path/cầu rankings and evidence |
| Research | [research](data/research/) | Randomness diagnostics, strategy lab, falsification |
| Model quality | [prob_eval](data/prob_eval/) | Out-of-sample probability evaluation |

---

## 🗃️ Complete Data Catalog

> [!TIP]
> Các section được thu gọn mặc định để trang dễ quan sát. Mở từng section để xem toàn bộ file và preview các bảng đại diện. **Không có thư mục con nào trong `data/` bị bỏ khỏi catalog.**

{_catalog()}

---

## 🩺 System Health

{_md_table(['Check', 'Value'], [
    ['Health', '✅ OK' if health.get('ok') else '⚠️ CHECK'],
    ['First date', health.get('first_date', '—')],
    ['Latest date', health.get('latest_date', '—')],
    ['Row count', health.get('row_count', '—')],
    ['Missing dates', health.get('missing_count', '—')],
    ['Full-history missing', health.get('full_missing_count', '—')],
    ['Duplicate dates', len(health.get('duplicate_dates', [])) if isinstance(health.get('duplicate_dates'), list) else '—'],
    ['Sparse validation', health.get('sparse_check', {}).get('ok', '—') if isinstance(health.get('sparse_check'), dict) else '—'],
])}

Sources: {_file_link(DATA / 'health.json')} · {_file_link(DATA / 'source_audit.json')}

---

<div align="center">

### VLA Data Navigation

[README](README.md) · [GitHub Pages](docs/index.html) · [Statistics](docs/statistics.html) · [AI/ML Dashboard](docs/dashboard.html) · [Research Lab](docs/research-lab.html) · [Model Quality](docs/model-quality.html)

<sub>Generated from committed repository data. Do not hand-edit this file; update the generator instead.</sub>

</div>
"""

    OUT.write_text(dashboard, encoding="utf-8")
    print(f"Wrote: {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

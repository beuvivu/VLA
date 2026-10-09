"""Benchmark tái lập: seed → train prefix → holdout score-before-learn.

Chạy trong vietlott: PYTHONPATH=src python scripts/evaluate_adaptive.py --help.
Không chạy collector, ghi checkpoint mô hình hay sửa ledger live.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory

from vietlott_engine.crawler.product_store import ProductStore
from vietlott_engine.forecast.data import load_series
from vlm.forecast.evaluation import compare_runs, evaluate_series
from vlm.forecast.pipeline import MLConfig


def _write_report(path: Path, report: dict) -> None:
    """Thay báo cáo nguyên tử; giữ báo cáo cũ nếu serialize/write lỗi."""
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    if path.suffix == '.gz':
        raw = gzip.compress(raw, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Chạy cấu hình cố định và ghi provenance/trace ngoài mẫu."""
    parser = argparse.ArgumentParser(description='Đánh giá Vietlott ngoài mẫu, không tạo chứng nhận live')
    parser.add_argument('--seed-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--adaptive', action='store_true')
    parser.add_argument('--products', nargs='+', default=['mega645','power655','lotto535','keno','bingo18','max3d','max3dpro'])
    parser.add_argument('--draws', type=int, default=600)
    parser.add_argument('--initial-draws', type=int, default=400)
    parser.add_argument('--compare-with', type=Path)
    args = parser.parse_args(argv)
    if args.compare_with is not None and args.output.resolve() == args.compare_with.resolve():
        parser.error('Output must differ from the comparison baseline')
    if not 1 < args.draws <= 1000 or not 1 <= args.initial_draws < args.draws:
        parser.error('Require 1 <= initial-draws < draws <= 1000')
    if len(args.products) != len(set(args.products)):
        parser.error('Products must be unique')
    config = MLConfig(bootstrap=args.draws, warmup=32, tree_every=64, tree_buffer=64,
                      search_nodes=50, seed=20261003, adaptive=args.adaptive)
    environment = {'python':platform.python_version()}
    for package in ('numpy','scipy','scikit-learn','pydantic','xgboost','lightgbm'):
        try:
            environment[package] = version(package)
        except PackageNotFoundError:
            environment[package] = None
    report = {'protocol':'retrospective_prequential_fixed_split', 'label':args.label,
        'initial_draws':args.initial_draws, 'holdout_draws':args.draws-args.initial_draws,
        'config':config.model_dump(mode='json'), 'environment':environment,
        'started_at':datetime.now(timezone.utc).isoformat(), 'results':[], 'live_certification':False,
        'target_date_policy':'known_draw_date_conditioning; fast products have no verified live slot',
        'brier_definition':'sum of component mean squared marginal errors; digit counts normalized per draw',
        'hits_definition':'top-k main-set overlap; not prize or jackpot probability'}
    with TemporaryDirectory() as temporary:
        for product in args.products:
            series = load_series(product, store=ProductStore(Path(temporary), args.seed_dir), seed_dir=args.seed_dir).tail(args.draws)
            if len(series) != args.draws:
                raise ValueError('Insufficient history for fixed split')
            result = evaluate_series(series, config, initial_draws=args.initial_draws)
            report['results'].append(result)
            _write_report(args.output, report)
            print(f"{product}: log_gain={result['mean_log_gain_nats']:.8f}; seconds={result['seconds']}", flush=True)
    if args.compare_with:
        raw = args.compare_with.read_bytes()
        baseline = json.loads(gzip.decompress(raw) if args.compare_with.suffix == '.gz' else raw)
        report['comparison_label'] = baseline['label']
        report['paired_comparison'] = compare_runs(baseline, report)
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    _write_report(args.output, report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

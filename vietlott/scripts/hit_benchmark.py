"""Chạy giao thức kiểm chứng xác suất và số khớp H (Mega 6/45, Power 6/55) và ghi artifact tái lập được.

    python scripts/hit_benchmark.py                       # cả hai sản phẩm, gồm bộ ML (~25 phút)
    python scripts/hit_benchmark.py --products mega645 --no-ml

Ghi ``reports/vlm/hit-benchmark/<sản phẩm>.json.gz`` (mọi kỳ: π từng số, vé, điểm),
``reports/vlm/hit-benchmark/summary.json`` (không gồm từng kỳ) và báo cáo Markdown.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from vietlott_engine.paths import enter_project
from vlm.forecast.hit_benchmark import PROTOCOL, benchmark_product, promotion_decision, render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--products', default=','.join(PROTOCOL['products']))
    parser.add_argument('--out-dir', type=Path, default=Path('reports/vlm/hit-benchmark'))
    parser.add_argument('--report', type=Path, default=Path(f'reports/VLM_HIT_BENCHMARK_{PROTOCOL["registered_at"]}.md'))
    parser.add_argument('--no-ml', action='store_true', help='bỏ bộ ML đang chạy (nhanh; không đủ để đề bạt)')
    parser.add_argument('--render-only', action='store_true', help='dựng lại báo cáo từ artifact đã ghi, không chạy lại')
    args = parser.parse_args(argv)
    root = enter_project()
    results = {}
    if args.render_only:
        for product in args.products.split(','):
            with gzip.open(args.out_dir / f'{product}.json.gz', 'rt', encoding='utf-8') as stream:
                results[product] = json.load(stream)
        decision = promotion_decision(results)
        args.report.write_text(render_report(results, decision), encoding='utf-8')
        print('kết luận:', decision['verdict'])
        return 0
    for product in args.products.split(','):
        results[product] = benchmark_product(product, Path(root), include_ml=not args.no_ml)
        print(product, 'xong', round(results[product]['timings']['total_seconds'], 1), 'giây', flush=True)
    decision = promotion_decision(results)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for product, result in results.items():
        with gzip.open(args.out_dir / f'{product}.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False)
    summary = {'protocol': PROTOCOL, 'decision': decision,
               'results': {p: {k: v for k, v in r.items() if k != 'draws'} for p, r in results.items()}}
    (args.out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=1) + '\n', encoding='utf-8')
    args.report.write_text(render_report(results, decision), encoding='utf-8')
    print('kết luận:', decision['verdict'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

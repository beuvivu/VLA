'Demo ngoại tuyến, replay CSV theo thời gian và các lệnh dự báo/phản hồi bền vững.'
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .engine import PredictiveEngine


def _labels(value: str, n: int, k: int, separator: str = ';') -> tuple[int, ...]:
    parts = [p.strip() for p in value.split(separator)]
    if len(parts) != k or any(re.fullmatch(r'\d+', p) is None for p in parts):
        raise ValueError('Each outcome must contain exactly k integer labels.')
    result = tuple(sorted(int(p) for p in parts))
    if len(set(result)) != k or any(p >= n for p in result):
        raise ValueError('Outcome labels must be distinct and in 0..n-1.')
    return result


def read_csv(path: Path, n: int, k: int) -> list[tuple[int, tuple[int, ...]]]:
    'Kiểm tra toàn bộ CSV trước khi mở cơ sở dữ liệu.'
    records = []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ['cycle', 'outcome']:
            raise ValueError('CSV header must be exactly cycle,outcome; labels separated by semicolons.')
        for row in reader:
            if set(row) != {'cycle', 'outcome'} or row['cycle'] is None or row['outcome'] is None:
                raise ValueError('Malformed CSV record.')
            if re.fullmatch(r'\d+', row['cycle']) is None or int(row['cycle']) != len(records):
                raise ValueError('CSV cycles must be consecutive integers starting at zero.')
            records.append((len(records), _labels(row['outcome'], n, k)))
    if not records:
        raise ValueError('CSV has no observations.')
    return records


async def _execute(args: argparse.Namespace) -> dict:
    records = None
    source_hash = None
    if args.command == 'replay':
        path = Path(args.csv)
        records = read_csv(path, args.n, args.k)
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    engine = PredictiveEngine(args.n, args.k, args.database, args.seed)
    try:
        if args.command == 'predict':
            return await engine.predict(args.cycle)
        if args.command == 'observe':
            return await engine.observe(args.cycle, _labels(args.outcome, args.n, args.k, ','))
        if args.command == 'status':
            return {'next_cycle': engine.next_cycle, 'pending': engine.pending is not None,
                    'evidence': engine.meta.evidence(), 'calibration': engine.meta.diagnostics()}
        if args.command == 'demo':
            if args.cycles < 1:
                raise ValueError('cycles must be positive.')
            if args.database != ':memory:':
                raise ValueError('Demo uses an in-memory database; use replay for durable datasets.')
            generator = np.random.default_rng(args.seed)
            records = []
            for t in range(args.cycles):
                labels = (generator.choice(args.n, args.k, replace=False).tolist()
                          if args.mode == 'uniform' else [(t + j) % args.n for j in range(args.k)])
                records.append((t, tuple(sorted(labels))))
        log_losses, briers, adaptive_cycles = [], [], 0
        for cycle, labels in records:
            prediction = await engine.predict(cycle)
            result = await engine.observe(cycle, labels)
            log_losses.append(result['log_loss'])
            briers.append(result['brier'])
            adaptive_cycles += prediction['mode'] == 'adaptive'
        next_forecast = await engine.predict(engine.next_cycle)
        return {'data_kind': ('synthetic_no_real_world_accuracy_claim' if args.command == 'demo'
                              else 'chronological_backtest_not_live_validation'),
                'source_sha256': source_hash, 'cycles': len(records), 'adaptive_cycles': adaptive_cycles,
                'mean_issued_log_loss': float(np.mean(log_losses)),
                'uniform_log_loss': engine.meta.uniform_log_loss,
                'mean_issued_brier': float(np.mean(briers)), 'brier_definition': 'mean_over_n_labels',
                'next_forecast': next_forecast}
    finally:
        engine.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in ('demo', 'replay', 'predict', 'observe', 'status'):
        command = subparsers.add_parser(name)
        command.add_argument('--n', type=int, required=True)
        command.add_argument('--k', type=int, required=True)
        command.add_argument('--seed', type=int, default=42)
        command.add_argument('--database', default=':memory:')
        if name == 'demo':
            command.add_argument('--cycles', type=int, default=180)
            command.add_argument('--mode', choices=('uniform', 'cycle'), default='cycle')
        elif name == 'replay':
            command.add_argument('--csv', required=True)
        elif name in ('predict', 'observe'):
            command.add_argument('--cycle', type=int, required=True)
            if name == 'observe':
                command.add_argument('--outcome', required=True, help='Zero-based labels separated by commas.')
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_execute(args))
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

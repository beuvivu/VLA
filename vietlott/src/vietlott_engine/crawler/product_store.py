"""Store and sync for Keno, Bingo18, Max 3D, Max 3D Pro and Max 4D histories, and official
prize tables of Mega / Power / Lotto — with a fallback chain for when vietlott.vn is out of reach.

Layout: ``<data_dir>/products/<file>`` (same file names as ``data/seed``) plus
``exclusions.json``. Reading merges the bundled seed with the local store (store rows win on
equal draw ids) and leaves out draws Vietlott announced as *not confirmed*.

Sources (``--source``):

* ``vietlott``  — vietlott.vn results lists (AjaxPro). Vietnamese IPs only.
* ``nhanaz``    — community archive ``NhanAZ-Data/vietlott-research`` (GitHub raw, or a local
  folder via ``VQE_NHANAZ_DIR``); Keno/Bingo18 updated about every 10 minutes in the day;
  all 8 products + exclusions.
* ``mirror``    — ``vietvudanh/vietlott-data`` JSONL (Keno, Bingo18, Max 3D, Max 3D Pro). Với
  Keno/Bingo18 chỉ được nhập qua cổng hồ sơ :meth:`ProductSyncPipeline._vet_fast_mirror`
  (01-11-2026): trùng tuyệt đối mọi kỳ seed có xuất xứ chính thức mà nó chồng lên
  (≥ ``MIRROR_TRACK_RECORD_MIN``) và mọi kỳ đăng lại độc lập của kho cộng đồng mà nó chồng lên
  (≥ ``MIRROR_CROSS_CHECK_MIN``).
* ``canonical`` — ``pqminh-4/vietlott-data`` canonical records (Max 3D, Max 3D Pro).
* ``v130``      — the snapshot of Vietlott Quant Engine 1.3.0 (``VQE_V130_DIR``).
* ``auto``      — the first of ``VQE_FALLBACK_ORDER`` that answers (default vietlott → nhanaz →
  mirror/canonical → v130); every attempt is in the report.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from vietlott_engine.core.exceptions import SourceError
from vietlott_engine.core.logging import get_logger
from vietlott_engine.core.models import Draw
from vietlott_engine.core.prizes import PrizeRecord
from vietlott_engine.core.products import (
    EXCLUSIONS_FILE,
    SEED_FILES,
    ProductCode,
    ProductHistory,
    drop_ids,
    get_product,
    history_to_rows,
    load_exclusions,
    parse_product_rows,
    read_jsonl,
    write_jsonl,
)
from vietlott_engine.crawler.http import AsyncHttpClient
from vietlott_engine.crawler.product_integrity import contiguous_results, finish_store_write, identities, parse_fast_rows
from vietlott_engine.forecast.schedule import VN

log = get_logger(__name__)

PRODUCTS = tuple(SEED_FILES)
MIRROR_FILES = {ProductCode.KENO: "keno.jsonl", ProductCode.BINGO18: "bingo18.jsonl", ProductCode.MAX3D: "3d.jsonl", ProductCode.MAX3D_PRO: "3d_pro.jsonl"}
CANONICAL_FILES = {ProductCode.MAX3D: "max3d.jsonl", ProductCode.MAX3D_PRO: "max3d_pro.jsonl"}
SOURCE_ALIASES = {"github_mirror": "mirror"}
FAST_PRODUCTS = {ProductCode.KENO, ProductCode.BINGO18}

# Cổng hồ sơ kiểm chứng của bản sao cộng đồng cho Keno/Bingo18 (01-11-2026).
#
# Từ 19-10-2026 vietlott.vn trả thử thách Cloudflare cho runner và kho cộng đồng chỉ còn đăng lại
# kết quả từ trang thứ cấp, nên không nguồn nào mang dấu «chính thức» và hai sản phẩm đứng yên.
# Bản sao chỉ được nhận khi chính nó chứng minh độ tin, đo lại MỖI lượt:
#
# * Hồ sơ: trùng tuyệt đối mọi kỳ của seed có xuất xứ chính thức mà nó chồng lên, ít nhất
#   ``MIRROR_TRACK_RECORD_MIN`` kỳ, không lệch kỳ nào. Không lệch trong n kỳ ⇒ cận trên 95% của tỉ lệ
#   sai mỗi kỳ là 3/n («quy tắc ba»): 10 000 kỳ ⇒ ≤ 3·10⁻⁴. Đo 01-11-2026: 86 462 kỳ Keno và
#   92 954 kỳ Bingo18 chồng nhau, 0 lệch. CHỈ đếm seed: kho sản phẩm không lưu xuất xứ từng dòng,
#   và sau lần nhập đầu nó chứa chính dòng của bản sao — đếm vào là tự chứng nhận.
# * Đối chiếu độc lập trên phần MỚI: hồ sơ cũ không thấy được lỗi vừa phát sinh (đổi khuôn trang,
#   lệch mã kỳ), nên bản sao còn phải trùng tuyệt đối mọi kỳ «trang đăng lại» của kho cộng đồng
#   (nguồn thu thập khác) mà nó chồng lên, ít nhất ``MIRROR_CROSS_CHECK_MIN`` kỳ. Lỗi hệ thống làm
#   lệch gần như mọi kỳ chồng nhau, nên 50 kỳ đủ để thấy. Đo 01-11-2026: 1 509 kỳ Keno và 1 558 kỳ
#   Bingo18 tháng 10, 0 lệch.
# * Một kỳ lệch ở bất kỳ phép so nào ⇒ loại CẢ bản sao lượt ấy. Mọi phép kiểm sẵn có của đường
#   nhập (mâu thuẫn với kỳ đã lưu, ngày tương lai, mã kỳ liên tục, thông báo loại kỳ) vẫn áp dụng.
KNOWN_GAPS_FILE = "known_gaps.json"
MIRROR_TRACK_RECORD_MIN = 10_000
MIRROR_CROSS_CHECK_MIN = 50
# Cửa sổ đối chiếu NEO THEO NGÀY MỚI NHẤT CỦA BẢN SAO, không theo ngày của kho: sau lần nhập đầu, kho
# cộng đồng tải từ ngày của kho chỉ còn các kỳ MỚI HƠN bản sao (nó đăng lại mỗi 10 phút, bản sao chỉ
# cập nhật lúc ~00:00 và ~12:00 UTC), nên phép đối chiếu ra 0 và cổng từ chối mọi lượt sau (01-11-2026).
MIRROR_CROSS_CHECK_DAYS = 31
OFFICIAL_SEED_SOURCES = frozenset({'vietlott.vn/list', 'nhanaz:official_vietlott'})


class ProductStore:
    def __init__(self, data_dir: Path, seed_dir: Path | None = None) -> None:
        self.dir = Path(data_dir) / "products"
        self.seed_dir = Path(seed_dir) if seed_dir else None

    def _rows(self, path: Path) -> list[dict]:
        return read_jsonl(path) if path.exists() else []

    def exclusions(self) -> dict[str, set[int]]:
        return load_exclusions(self.seed_dir, self.dir)

    def known_gaps(self) -> dict[str, list[tuple[int, int]]]:
        """Khoảng hở lịch sử đã kiểm là không nguồn nào có (``seed/known_gaps.json``, 01-11-2026).

        Chỉ đổi BÁO CÁO: khoảng hở nằm trọn trong danh sách không còn là lỗi đồng bộ. Không phải
        thông báo loại kỳ, không thêm hay suy ra kết quả nào; khoảng hở mới vẫn là lỗi.
        """
        path = self.seed_dir / KNOWN_GAPS_FILE if self.seed_dir else None
        if path is None or not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {product: [(int(a), int(b)) for a, b in ranges] for product, ranges in data.get("products", {}).items()}

    def load(self, product: str | ProductCode, include_unconfirmed: bool = False) -> ProductHistory:
        code = get_product(product)
        if code not in SEED_FILES:
            raise KeyError(f"{code.value} is a matrix game; use the draw repository")
        rows = (self._rows(self.seed_dir / SEED_FILES[code]) if self.seed_dir else []) + self._rows(self.dir / SEED_FILES[code])
        sources = [s for s, p in (("seed", self.seed_dir / SEED_FILES[code] if self.seed_dir else None), ("store", self.dir / SEED_FILES[code])) if p is not None and p.exists()]
        h, _ = parse_product_rows(code, rows, source="+".join(sources) or "empty")
        return h if include_unconfirmed else drop_ids(h, self.exclusions().get(code.value, set()))

    def max_draw_id(self, product: ProductCode) -> int | None:
        h = self.load(product, include_unconfirmed=True)
        return int(h.draw_ids.max()) if len(h) else None

    def last_date(self, product: ProductCode) -> date | None:
        h = self.load(product, include_unconfirmed=True)
        return h.dates.max().astype("datetime64[D]").astype(date) if len(h) else None

    def upsert(self, product: ProductCode, rows: list[dict], source: str) -> tuple[int, int]:
        """Validate and merge ``rows`` into the store file → (new draw ids, rejected)."""
        new, rejected = parse_product_rows(product, rows, source)
        if not len(new):
            return 0, len(rejected)
        known = set(self.load(product, include_unconfirmed=True).draw_ids.tolist())
        path = self.dir / SEED_FILES[product]
        old, _ = parse_product_rows(product, self._rows(path), "store")
        merged = {int(i): r for i, r in zip(old.draw_ids, history_to_rows(old))}
        merged.update({int(i): r for i, r in zip(new.draw_ids, history_to_rows(new))})
        write_jsonl(path, [merged[i] for i in sorted(merged)])
        return len(set(new.draw_ids.tolist()) - known), len(rejected)

    def add_exclusions(self, items: list[dict]) -> int:
        """Record not-confirmed draws (issuer notices) in the store → number added."""
        if not items:
            return 0
        path = self.dir / EXCLUSIONS_FILE
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        known = {(e["product"], int(e["draw_id"])) for e in current} | {(p, i) for p, ids in load_exclusions(self.seed_dir).items() for i in ids}
        added = [e for e in items if (e["product"], int(e["draw_id"])) not in known]
        if added:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(current + added, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(added)

    def coverage(self) -> list[dict]:
        out = []
        excl = self.exclusions()
        for code in PRODUCTS:
            try:
                out.append(self.load(code).coverage() | {"excluded_not_confirmed": len(excl.get(code.value, set()))})
            except (FileNotFoundError, ValueError) as exc:
                out.append({"product": code.value, "draws": 0, "error": str(exc)})
        return out


@dataclass
class ProductSyncReport:
    product: str
    source: str
    fetched: int
    inserted: int
    rejected: int
    total_after: int
    last_id: int | None
    last_date: str | None
    missing_ids_inside_range: int
    elapsed_s: float
    error: str | None = None
    source_used: str | None = None
    exclusions_added: int = 0
    attempts: list[dict] = field(default_factory=list)
    continuity: dict = field(default_factory=dict)
    # Nguồn của kỳ có mã LỚN NHẤT vừa nhận (``source_used`` ghép mọi nguồn có góp dòng): độ mới đo theo
    # nhịp của chính nguồn đã đưa kho tới kỳ mới nhất (`vlm.updates.runner`).
    latest_source: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ProductSyncPipeline:
    def __init__(
        self,
        client: AsyncHttpClient,
        store: ProductStore,
        *,
        vietlott_base_url: str,
        mirror_base_url: str,
        canonical_base_url: str,
        bootstrap_cookie: bool = True,
        pages_per_batch: int = 4,
        nhanaz_base_url: str | None = None,
        nhanaz_dir: Path | None = None,
        v130_dir: Path | None = None,
        fallback_order: list[str] | None = None,
        source_timeout_s: float = 20,
        archive_timeout_s: float = 90,
    ) -> None:
        from vietlott_engine.crawler.sources.nhanaz import NHANAZ_RAW_BASE

        self.client = client
        self.store = store
        self.vietlott_base_url = vietlott_base_url
        self.mirror_base_url = mirror_base_url.rstrip("/")
        self.canonical_base_url = canonical_base_url.rstrip("/")
        self.bootstrap_cookie = bootstrap_cookie
        self.pages_per_batch = pages_per_batch
        self.nhanaz_base_url = nhanaz_base_url or NHANAZ_RAW_BASE
        self.nhanaz_dir = nhanaz_dir
        self.v130_dir = v130_dir
        self.fallback_order = [SOURCE_ALIASES.get(s, s) for s in (fallback_order or ["vietlott", "nhanaz", "mirror", "canonical", "v130"])]
        self._pending_exclusions: list[dict] = []
        self.source_timeout_s = source_timeout_s
        self.archive_timeout_s = archive_timeout_s
        self._since_id: int | None = None
        self._since_date: date | None = None
        self._fetch_rejected: list[dict] = []
        self._rejected_exclusions: list[dict] = []
        self._archive_secondary: dict[ProductCode, list[dict]] = {}
        self._source_audit: dict | None = None

    async def _jsonl(self, url: str) -> list[dict]:
        text = (await self.client.get(url)).text
        return await asyncio.to_thread(lambda: [json.loads(line) for line in text.splitlines() if line.strip()])

    def _archive(self):  # type: ignore[no-untyped-def]
        from vietlott_engine.crawler.sources.nhanaz import NhanAZArchive

        return NhanAZArchive(local_dir=self.nhanaz_dir) if self.nhanaz_dir else NhanAZArchive(self.client, self.nhanaz_base_url)

    def _official_seed_identities(self, product: ProductCode) -> dict[int, tuple]:
        """Kỳ của seed có xuất xứ chính thức → (ngày, kết quả) theo đúng chuẩn của ``identities``."""
        if self.store.seed_dir is None:
            return {}
        rows = [r for r in self.store._rows(self.store.seed_dir / SEED_FILES[product])
                if r.get('src') in OFFICIAL_SEED_SOURCES]
        parsed, _, _ = parse_fast_rows(product, rows, 'seed')
        return identities(parsed)

    def _vet_fast_mirror(self, product: ProductCode, rows: list[dict], secondary_rows: list[dict]) -> None:
        """Cổng hồ sơ kiểm chứng của bản sao Keno/Bingo18; ném ``SourceError`` khi chưa đủ tin.

        Luật và lý do: chú thích ở ``MIRROR_TRACK_RECORD_MIN``. Kết quả đo ghi vào
        ``self._source_audit`` để báo cáo đồng bộ in ra từng lượt.
        """
        parsed, _, duplicates = parse_fast_rows(product, rows, 'mirror')
        mirror = identities(parsed)
        official = self._official_seed_identities(product)
        secondary_rows, _, _ = parse_fast_rows(product, secondary_rows, 'nhanaz')
        secondary = identities(secondary_rows)
        track = [did for did in mirror if did in official]
        track_bad = sorted(did for did in track if mirror[did] != official[did])
        cross = [did for did in mirror if did in secondary]
        cross_bad = sorted(did for did in cross if mirror[did] != secondary[did])
        self._source_audit = {
            'rule': 'fast-mirror-track-record-v1',
            'official_overlap': len(track), 'official_mismatches': len(track_bad),
            'cross_checked': len(cross), 'cross_mismatches': len(cross_bad),
            'duplicates_conflicting': len(duplicates),
            'mismatched_ids': (track_bad + cross_bad)[:20],
        }
        if duplicates or track_bad or cross_bad:
            raise SourceError('unverified fast-game mirror: disagrees with official or independent results; not imported')
        if len(track) < MIRROR_TRACK_RECORD_MIN:
            raise SourceError(f'unverified fast-game mirror: official track record {len(track)} < '
                              f'{MIRROR_TRACK_RECORD_MIN} draws; not imported')
        if len(cross) < MIRROR_CROSS_CHECK_MIN:
            raise SourceError(f'unverified fast-game mirror: independent cross-check {len(cross)} < '
                              f'{MIRROR_CROSS_CHECK_MIN} draws; not imported')

    def chain(self, product: ProductCode) -> list[str]:
        """Sources of ``auto`` that can serve this product."""
        out = []
        for s in self.fallback_order:
            if (s == "mirror" and product not in MIRROR_FILES) or (s == "canonical" and product not in CANONICAL_FILES) or (s == "v130" and self.v130_dir is None):
                continue
            if s == "vietlott" and product == ProductCode.MAX4D:
                continue  # discontinued: no live list
            if s == "xskt":
                continue  # chỉ có Mega/Power/Lotto (đường SyncPipeline), không có sản phẩm này
            out.append(s)
        return out

    async def fetch(self, product: ProductCode, source: str, max_pages: int, full: bool) -> list[dict]:
        source = SOURCE_ALIASES.get(source, source)
        if source == "vietlott":
            from vietlott_engine.crawler.sources.vietlott_official import VietlottProductSource

            src = VietlottProductSource(self.client, self.vietlott_base_url, self.pages_per_batch, self.bootstrap_cookie)
            since = None if full else self._since_id
            return await src.fetch_pages(product, max_pages=max_pages, since_id=since)
        if source == "nhanaz":
            archive = self._archive()
            got = await archive.draws(product, since=None if full else self._since_date,
                                      verified_only=product in FAST_PRODUCTS)
            self._fetch_rejected = got.rejected
            if product in FAST_PRODUCTS:
                self._archive_secondary[product] = got.secondary
            self._pending_exclusions += [e for e in await archive.exclusions(verified_only=product in FAST_PRODUCTS)
                                         if e["product"] == product.value]
            self._rejected_exclusions = [e for e in archive.rejected_exclusions if e.get('product')==product.value]
            return got.rows
        if source == "v130":
            if product in FAST_PRODUCTS:
                raise SourceError('unverified fast-game historical snapshot; use verified archive or official pages')
            if self.v130_dir is None:
                raise SourceError("v130 source needs VQE_V130_DIR (Vietlott Quant Engine 1.3.0 folder)")
            from vietlott_engine.crawler.sources.vqe130 import import_v130, v130_exclusions

            got = import_v130(self.v130_dir, product)
            self._pending_exclusions += [e for e in v130_exclusions(self.v130_dir) if e["product"] == product.value]
            return got.rows
        if source == "mirror":
            if product not in MIRROR_FILES:
                raise SourceError(f"no mirror file for {product.value}")
            rows = await self._jsonl(f"{self.mirror_base_url}/{MIRROR_FILES[product]}")
            if product in FAST_PRODUCTS:
                dates = [str(r.get('date', ''))[:10] for r in rows if r.get('date')]
                since = (date.fromisoformat(max(dates)) - timedelta(days=MIRROR_CROSS_CHECK_DAYS)) if dates else self._since_date
                got = await self._archive().draws(product, since=since, verified_only=True)
                await asyncio.to_thread(self._vet_fast_mirror, product, rows, got.secondary)
            return rows
        if source == "canonical":
            if product not in CANONICAL_FILES:
                raise SourceError(f"no canonical records for {product.value}; use --source nhanaz, mirror or vietlott")
            return await self._jsonl(f"{self.canonical_base_url}/{CANONICAL_FILES[product]}")
        raise SourceError(f"unknown product source {source!r}")

    async def run(self, product: ProductCode, source: str = "auto", max_pages: int = 50, full: bool = False,
                  *, before_upsert: Callable[[ProductHistory, str], None] | None = None) -> ProductSyncReport:
        t0 = time.perf_counter()
        self._pending_exclusions = []
        history = await asyncio.to_thread(self.store.load, product, include_unconfirmed=True)
        self._since_id = int(history.draw_ids.max()) if len(history) else None
        self._since_date = date.fromisoformat(str(history.dates.max())) if len(history) else None
        if product in FAST_PRODUCTS:
            return await self._run_fast(product, source, max_pages, full, history, t0, before_upsert)
        attempts: list[dict] = []
        rows: list[dict] = []
        used = None
        best_rows, best_source, best_id, best_parsed = [], None, -1, None
        known_max = self._since_id or 0
        for s in self.chain(product) if source == "auto" else [source]:
            try:
                budget = self.archive_timeout_s if s == 'nhanaz' else self.source_timeout_s
                rows = await asyncio.wait_for(self.fetch(product, s, max_pages, full), budget)
            except (SourceError, OSError, ValueError, TimeoutError) as exc:
                msg = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
                attempts.append({"source": s, "ok": False, "rows": 0, "error": msg})
                log.warning("%s: source %s failed (%s)", product.value, s, msg)
                continue
            attempts.append({"source": s, "ok": True, "rows": len(rows), "error": None})
            parsed, _ = await asyncio.to_thread(parse_product_rows, product, rows, s)
            source_max = int(parsed.draw_ids.max()) if len(parsed) else -1
            if source_max > best_id:
                best_rows, best_source, best_id, best_parsed = rows, s, source_max, parsed
            if source == 'auto' and source_max <= known_max:
                attempts[-1]['stale'] = True
                continue
            used = s
            break
        if used is None and best_source is not None:
            rows, used = best_rows, best_source
            parsed = best_parsed
        error = None if used else "; ".join(f"{a['source']}: {a['error']}" for a in attempts)
        if rows and before_upsert is not None:
            # Hook nhận đúng dòng đã xác thực, bỏ cả thông báo loại kỳ mới tải.
            excluded = self.store.exclusions().get(product.value, set()) | {
                int(e['draw_id']) for e in self._pending_exclusions if e['product'] == product.value}
            before_upsert(drop_ids(parsed, excluded), used or source)
        inserted, rejected = self.store.upsert(product, rows, used or source) if rows else (0, 0)
        excl = self.store.add_exclusions(self._pending_exclusions)
        h = self.store.load(product)
        cov = h.coverage()
        return ProductSyncReport(
            product=product.value,
            source=source,
            fetched=len(rows),
            inserted=inserted,
            rejected=rejected,
            total_after=len(h),
            last_id=cov["last_id"],
            last_date=cov["last_date"],
            missing_ids_inside_range=cov["missing_ids_inside_range"],
            elapsed_s=round(time.perf_counter() - t0, 3),
            error=error,
            source_used=used,
            exclusions_added=excl,
            attempts=attempts,
        )

    async def _run_fast(self, product, source, max_pages, full, history, t0, before_upsert):  # type: ignore[no-untyped-def]
        known = await asyncio.to_thread(identities, history)
        known_max = max(known,default=0)
        excluded = (await asyncio.to_thread(self.store.exclusions)).get(product.value, set())
        candidates, origins, attempts = {}, {}, []
        blocked_ids = set()
        conflicts = set()
        validation_errors = []
        today = datetime.now(VN).date().isoformat()
        for s in self.chain(product) if source == 'auto' else [source]:
            # Bản sao tải cả lịch sử (~13 MB) và có thể phải tải kho đối chiếu: ngân sách như kho.
            budget = self.archive_timeout_s if s in ('nhanaz', 'mirror') else self.source_timeout_s
            started = time.perf_counter()
            self._fetch_rejected = []
            self._rejected_exclusions = []
            self._source_audit = None
            attempt = {'source':s, 'ok':False, 'rows':0, 'rejected':0, 'error':None,
                       'timeout_s':budget}
            attempts.append(attempt)
            try:
                try:
                    rows = await asyncio.wait_for(self.fetch(product, s, max_pages, full), budget)
                finally:
                    if self._source_audit is not None:
                        attempt['audit'] = self._source_audit
                parsed, rejected, duplicates = await asyncio.to_thread(parse_fast_rows, product, rows, s)
                incoming = await asyncio.to_thread(identities, parsed)
                attempt.update(rows=len(rows), rejected=len(rejected)+len(self._fetch_rejected))
                blocked_ids.update(int(str(r['draw_id']).lstrip('#')) for r in self._fetch_rejected
                                   if str(r.get('draw_id','')).lstrip('#').isdigit())
                if self._rejected_exclusions:
                    attempt['rejected_exclusions'] = len(self._rejected_exclusions)
                    validation_errors.append(f'{s}: unverified exclusion notices rejected')
                bad = list(duplicates)
                invalid = [did for did,value in incoming.items() if did<=0 or value[0]>today
                           or (known and did>known_max and value[0]<known[known_max][0])]
                for did,value in incoming.items():
                    previous = candidates.get(did) or known.get(did)
                    correction = full and s == 'vietlott' and did in known
                    if (previous is not None and previous != value and not correction) or did in conflicts:
                        bad.append(did)
                if rejected or invalid or bad:
                    # Không báo thành công khi có dòng sai. Vẫn giữ được đoạn
                    # liên tục đã xác thực trước lỗi; nguồn mâu thuẫn bị loại.
                    attempt.update(rejected=attempt['rejected']+len(invalid),
                                   conflicting_ids=sorted(set(bad))[:20],
                                   conflicting_count=len(set(bad)),error='source rows failed validation or conflict checks')
                    raw_ids={int(str(r['id']).lstrip('#')) for r in rows
                             if str(r.get('id','')).lstrip('#').isdigit()}
                    blocked_ids.update(raw_ids-set(incoming) | set(invalid) | set(bad))
                    for did in bad:
                        if did not in known:
                            candidates.pop(did,None)
                            conflicts.add(did)
                    validation_errors.append(f'{s}: source rows failed validation or conflict checks')
                    if bad:
                        if source != 'auto':
                            break
                        continue
                    for did in invalid:
                        incoming.pop(did,None)
                for did, value in incoming.items():
                    correction = full and s == 'vietlott' and did in known
                    if correction:
                        candidates[did] = value
                    else:
                        candidates.setdefault(did, value)
                    origins.setdefault(did, s)
                excluded.update(int(e['draw_id']) for e in self._pending_exclusions if e['product']==product.value)
                accepted, continuity = await asyncio.to_thread(contiguous_results, known, candidates, excluded)
                new = [r for r in accepted if r['id'] not in known]
                attempt['ok'] = bool(incoming) and not (rejected or invalid or bad)
                advanced = any(r['id']>known_max for r in new)
                attempt['stale'] = not advanced
                if not incoming and not attempt['error']:
                    attempt['error'] = 'unverified or invalid archive rows' if attempt['rejected'] else 'no verified results'
                if source != 'auto' or (attempt['ok'] and advanced and not continuity['missing_ranges']
                                         and not continuity['historical_missing_ranges']):
                    break
            except (SourceError, OSError, ValueError, OverflowError, TimeoutError) as exc:
                attempt['error'] = (f'source deadline exceeded ({budget:g}s)' if isinstance(exc, TimeoutError)
                                    else (str(exc).splitlines() or [type(exc).__name__])[0][:300])
                log.warning('%s: source %s failed (%s)', product.value, s, attempt['error'])
            finally:
                attempt['elapsed_s'] = round(time.perf_counter()-started,3)
        accepted, continuity = await asyncio.to_thread(contiguous_results, known, candidates, excluded)
        delta = [r for r in accepted if known.get(r['id']) != (r['date'],tuple(r['result']))]
        used = '+'.join(dict.fromkeys(origins[r['id']] for r in delta)) or next(
            (a['source'] for a in attempts if a['ok']), None)
        errors = list(validation_errors)
        if continuity['missing_ranges']:
            errors.append('missing verified draw ranges: '+str(continuity['missing_ranges'][:10]))
        if conflicts:
            errors.append('conflicting source results: '+str(sorted(conflicts)[:20]))
        known_gaps = self.store.known_gaps().get(product.value, [])
        unexplained = [g for g in continuity['historical_missing_ranges']
                       if not any(a <= g[0] and g[1] <= b for a, b in known_gaps)]
        continuity['acknowledged_gaps'] = len(continuity['historical_missing_ranges']) - len(unexplained)
        if unexplained:
            errors.append('historical verified draw gaps remain: '+str(unexplained[:10]))
        if not used:
            errors.append('; '.join(f"{a['source']}: {a['error'] or 'no verified results'}" for a in attempts))
        continuity['unverified_rows'] = len(blocked_ids)
        # Cursor cũ không phải chứng nhận nguồn chính thức cho lịch sử đã nhập.
        continuity['latest_verified'] = max(candidates,default=None)
        continuity['latest_observed'] = max(continuity['latest_observed'] or 0,max(blocked_ids,default=0)) or None
        # Một số kỳ đã xác thực không được che các kỳ mới hơn còn pending.
        pending_new = blocked_ids - set(candidates) - excluded
        through = continuity['contiguous_through'] or 0
        # Kỳ đúng cấu trúc của kho cộng đồng chỉ bị chặn vì xuất xứ thứ cấp là kỳ CHỜ XÁC MINH: chúng luôn
        # đi trước bản sao (đăng lại mỗi 10 phút, bản sao 12 giờ một lần). Độ trễ ấy do quy tắc độ mới
        # (`vlm.updates.runner`) canh. Kỳ bị chặn vì lý do khác (sai cấu trúc, mâu thuẫn) vẫn là lỗi.
        secondary_ids = {int(r['id']) for r in self._archive_secondary.get(product, [])}
        awaiting = {i for i in pending_new if i > through and i in secondary_ids}
        continuity['awaiting_verification'] = len(awaiting)
        if any(i > through for i in pending_new - awaiting):
            errors.append('new source rows remain unverified or invalid')
        if delta and before_upsert is not None:
            validated, _ = await asyncio.to_thread(parse_product_rows, product, delta, used or source)
            before_upsert(validated, used or source)
        def persist():
            inserted, rejected = self.store.upsert(product, delta, used or source) if delta else (0,0)
            h = self.store.load(product)
            return inserted, rejected, len(h), h.coverage()
        # Tệp loại kỳ được chia sẻ giữa sản phẩm: ghi nhỏ này ở cùng event loop
        # để hai thread không đọc-sửa-ghi đè thông báo của nhau.
        added = self.store.add_exclusions(self._pending_exclusions)
        inserted, rejected, total, cov = await finish_store_write(persist)
        return ProductSyncReport(product=product.value, source=source, fetched=sum(a['rows'] for a in attempts),
            inserted=inserted, rejected=rejected+sum(a['rejected'] for a in attempts), total_after=total,
            last_id=cov['last_id'], last_date=cov['last_date'], missing_ids_inside_range=cov['missing_ids_inside_range'],
            elapsed_s=round(time.perf_counter()-t0,3), error='; '.join(errors) or None, source_used=used,
            exclusions_added=added, attempts=attempts, continuity=continuity,
            latest_source=origins.get(max(r['id'] for r in delta)) if delta else None)


# ----------------------------------------------------------------- official prize data
def _prefer_prize_record(current, incoming):  # type: ignore[no-untyped-def]
    """Chọn nguyên bảng giải, không ghép giá trị rồi đổi nhãn nguồn của chúng.

    Nguồn ưu tiên chỉ thay thế bảng cũ nếu không làm mất trường đã biết. Nguồn
    phụ được bổ sung trường thiếu khi mọi trường chung khớp bảng đang có.
    """
    rank = lambda origin: 3 if origin.startswith('vietlott') else 2 if origin.startswith('canonical') else 1
    pairs = ((current.winners, incoming.winners),
             (current.jackpot_pots or {}, incoming.jackpot_pots or {}))
    covers = all(set(old).issubset(new) for old, new in pairs)
    if rank(incoming.source) >= rank(current.source):
        return incoming if covers else current
    adds = any(set(new) - set(old) for old, new in pairs)
    agrees = all(all(new.get(key) == value for key, value in old.items()) for old, new in pairs)
    return incoming if covers and adds and agrees else current


@dataclass
class CanonicalPrizeReport:
    game: str
    source: str
    records: int
    draws_inserted: int
    prize_records: int
    prize_records_inserted: int
    with_jackpot_pots: int
    rejected: int
    elapsed_s: float
    error: str | None = None
    source_used: str | None = None
    attempts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


async def _prize_records(client, repository, spec, source: str, *, canonical_base_url: str, vietlott_base_url: str, last: int, bootstrap_cookie: bool, nhanaz_base_url: str | None, nhanaz_dir: Path | None, v130_dir: Path | None) -> list[dict]:  # type: ignore[no-untyped-def]
    from vietlott_engine.crawler.sources.vietlott_official import VietlottOfficialSource

    if source == "canonical":
        text = (await client.get(f"{canonical_base_url.rstrip('/')}/{spec.code.value}.jsonl")).text
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if source == "vietlott":
        ids = sorted(d.draw_id for d in repository.load(spec.code))[-last:]
        return await VietlottOfficialSource(client, vietlott_base_url, bootstrap_cookie=bootstrap_cookie).fetch_canonical(spec, ids)
    if source == "nhanaz":
        from vietlott_engine.crawler.sources.nhanaz import NHANAZ_RAW_BASE, NhanAZArchive

        archive = NhanAZArchive(local_dir=nhanaz_dir) if nhanaz_dir else NhanAZArchive(client, nhanaz_base_url or NHANAZ_RAW_BASE)
        return (await archive.draws(ProductCode(spec.code.value))).rows
    if source == "v130":
        if v130_dir is None:
            raise SourceError("v130 source needs VQE_V130_DIR (Vietlott Quant Engine 1.3.0 folder)")
        from vietlott_engine.crawler.sources.vqe130 import import_v130

        return import_v130(v130_dir, ProductCode(spec.code.value)).rows
    raise SourceError(f"unknown prize source {source!r}")


async def sync_canonical_prizes(
    client: AsyncHttpClient,
    repository,  # type: ignore[no-untyped-def]
    spec,  # type: ignore[no-untyped-def]
    *,
    source: str,
    canonical_base_url: str,
    vietlott_base_url: str,
    last: int = 20,
    bootstrap_cookie: bool = True,
    nhanaz_base_url: str | None = None,
    nhanaz_dir: Path | None = None,
    v130_dir: Path | None = None,
    fallback_order: list[str] | None = None,
    before_upsert: Callable[[list[Draw], list[PrizeRecord]], None] | None = None,
) -> CanonicalPrizeReport:
    """Official prize tables → repository.

    ``canonical``: the ``pqminh-4`` record file. ``vietlott``: detail pages of the ``last`` most
    recent stored draws (from Vietnam). ``nhanaz`` / ``v130``: community archive / 1.3.0
    snapshot. ``auto`` tiếp tục đến khi các kỳ gần nhất có bảng giải đúng kỳ,
    thay vì dừng ở một kho lịch sử còn thiếu dữ liệu tài chính mới."""
    from vietlott_engine.crawler.official_data import import_canonical

    t0 = time.perf_counter()
    order = [s for s in (fallback_order or ["vietlott", "canonical", "nhanaz", "v130"]) if not (s == "v130" and v130_dir is None)]
    attempts: list[dict] = []
    known = {d.draw_id: d for d in repository.load(spec.code)}
    targets = sorted(known)[-max(1, last):]
    prizes = {p.draw_id: p for p in repository.load_prizes(spec.code)}
    tiers = {t.name for t in spec.tiers}
    jackpots = {t.name for t in spec.tiers if t.is_jackpot}
    records = draws_inserted = prizes_inserted = rejected = 0
    imported_prizes = {}
    used = None
    for s in order if source == "auto" else [source]:
        try:
            rows = await asyncio.wait_for(_prize_records(
                client, repository, spec, s, canonical_base_url=canonical_base_url, vietlott_base_url=vietlott_base_url, last=last,
                bootstrap_cookie=bootstrap_cookie, nhanaz_base_url=nhanaz_base_url, nhanaz_dir=nhanaz_dir, v130_dir=v130_dir,
            ), 20)
        except (SourceError, OSError, ValueError, TimeoutError) as exc:
            attempts.append({"source": s, "ok": False, "rows": 0, "error": (str(exc).splitlines() or [type(exc).__name__])[0][:300]})
            continue
        records += len(rows)
        additions = []
        accepted = []
        for row in rows:
            if not isinstance(row, dict) or any(row.get(key) not in (None, spec.code.value)
                                                for key in ('game', 'game_type', 'product')):
                rejected += 1
                continue
            # Nhập từng row để bảng giải không mất liên kết với chính bộ số của nó.
            try:
                imp = import_canonical([row], spec.code)
            except (ValueError, TypeError, KeyError):
                rejected += 1
                continue
            rejected += len(imp.rejected)
            if not imp.draws:
                continue
            draw = imp.draws[0]
            current = known.get(draw.draw_id)
            if current is not None and (current.draw_date, current.numbers, current.bonus) != (draw.draw_date, draw.numbers, draw.bonus):
                rejected += 1
                continue
            if current is None:
                additions.append(draw)
                known[draw.draw_id] = draw
            for prize in imp.prizes:
                if prize.draw_date != draw.draw_date:
                    continue
                current = prizes.get(prize.draw_id)
                if current is not None and current.draw_date == prize.draw_date:
                    prize = _prefer_prize_record(current, prize)
                prizes[prize.draw_id] = prize
                imported_prizes[prize.draw_id] = prize
                accepted.append(prize)
        # Đồng bộ bảng giải không được sửa số quay để tự làm cho bảng giải khớp.
        if before_upsert is not None:
            before_upsert(additions, accepted)
        draws_inserted += repository.upsert(additions) if additions else 0
        prizes_inserted += repository.upsert_prizes(accepted) if accepted else 0
        missing = [did for did in targets if did not in prizes or prizes[did].draw_date != known[did].draw_date
                   or set(prizes[did].winners) != tiers or not jackpots.issubset(prizes[did].jackpot_pots or {})]
        attempts.append({'source': s, 'ok': bool(accepted), 'rows': len(rows),
                         'missing_draw_ids': missing, 'error': None if accepted else 'no matching prize tables'})
        if accepted:
            used = s
        if source != 'auto' or (accepted and not missing):
            break
    missing = [did for did in targets if did not in prizes or prizes[did].draw_date != known[did].draw_date
               or set(prizes[did].winners) != tiers or not jackpots.issubset(prizes[did].jackpot_pots or {})]
    error = ('missing current prize tables: ' + ', '.join(str(did) for did in missing)) if missing else None
    if not targets and not used:
        error = '; '.join(f"{a['source']}: {a['error']}" for a in attempts) or 'no matching prize tables'
    return CanonicalPrizeReport(
        game=spec.code.value,
        source=source,
        records=records,
        draws_inserted=draws_inserted,
        prize_records=len(imported_prizes),
        prize_records_inserted=prizes_inserted,
        with_jackpot_pots=sum(p.jackpot_pots is not None for p in imported_prizes.values()),
        rejected=rejected,
        elapsed_s=round(time.perf_counter() - t0, 3),
        error=error,
        source_used=used,
        attempts=attempts,
    )

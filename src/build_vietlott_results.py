"""Dựng dashboard và trang kết quả riêng cho từng sản phẩm Vietlott."""
from __future__ import annotations
import html,json,sqlite3
from pathlib import Path
from css_links import stylesheet_link
from page_output import write_page
from ui_theme import app_shell_open,app_shell_close
from vietlott_results import PRODUCTS as SOURCES, TRIPLE_GROUPS
from web_security import security_meta_tags

PRODUCTS={
"lotto535":("Lotto 5/35","vietlott-lotto-535.html","5 số + số đặc biệt"),
"mega645":("Mega 6/45","vietlott-mega-645.html","6 số"),
"power655":("Power 6/55","vietlott-power-655.html","6 số + số đặc biệt"),
"max3d":("Max 3D / Max 3D+","vietlott-max-3d.html","20 bộ ba số"),
"max3dpro":("Max 3D Pro","vietlott-max-3d-pro.html","20 bộ ba số"),
"keno":("Keno","vietlott-keno.html","20 số / kỳ"),
"bingo18":("Bingo18","vietlott-bingo18.html","3 số / kỳ"),
}

def rows(db,product,limit=120):
 return db.execute("""SELECT draw_id,draw_date,result_json,bonus,jackpot_1,jackpot_2,meta_json,source_url
 FROM draws WHERE product=? ORDER BY draw_date DESC,CAST(draw_id AS INTEGER) DESC LIMIT ?""",(product,limit)).fetchall()

def money(v):
 return f"{v:,}".replace(",",".")+" ₫" if v else "—"

def balls(values,bonus=""):
 out="".join(f'<span class="vl-ball">{html.escape(str(x))}</span>' for x in values)
 return out+(f'<span class="vl-plus">+</span><span class="vl-ball vl-ball--bonus">{html.escape(bonus)}</span>' if bonus else "")

def result_markup(product,result,bonus,meta):
 if product in ("lotto535","mega645","power655","keno"):return balls(result,bonus)
 if product=="bingo18":
  total=meta.get("sum",sum(map(int,result)));band=meta.get("band","")
  return balls(result)+f'<span class="vl-bingo-meta">Tổng <b>{total}</b> · {html.escape(str(band))}</span>'
 # Max 3D xếp Nhất/Nhì/Ba/Tư, Max 3D Pro xếp ĐB/Nhất/Nhì/Ba — lấy đúng nhóm bộ thu thập đã ghi.
 order=[(key,label,n) for key,label,n in TRIPLE_GROUPS.get(product,())]
 groups=meta.get("groups") or {}
 if not groups and order:
  i=0
  for key,_,n in order: groups[key]=result[i:i+n]; i+=n
 return '<div class="vl-3d">'+''.join(
  f'<div><small>{label}</small><span>{" · ".join(html.escape(x) for x in groups.get(key,[]))}</span></div>'
  for key,label,_ in order)+'</div>'

def card(product,row,compact=False):
 did,day,rj,bonus,j1,j2,mj,url=row; result=json.loads(rj);meta=json.loads(mj or "{}")
 jackpots=""
 if j1:jackpots+=f'<span>Jackpot: <b>{money(j1)}</b></span>'
 if j2:jackpots+=f'<span>Jackpot 2: <b>{money(j2)}</b></span>'
 return f'''<article class="vl-draw" data-date="{day}" data-id="{html.escape(did)}">
 <div class="vl-draw-head"><div><small>KỲ QUAY</small><strong>#{html.escape(did)}</strong></div><time>{html.escape(day)}</time></div>
 <div class="vl-result">{result_markup(product,result,bonus,meta)}</div>
 <div class="vl-jackpots">{jackpots}</div>
 </article>'''

STYLE="""
.vl-hero{position:relative;overflow:hidden;padding:28px;border:1px solid var(--ui-border);border-radius:26px;background:linear-gradient(135deg,var(--ui-surface),var(--ui-brand-soft));box-shadow:var(--ui-sh-sm);margin-bottom:20px}.vl-kicker{font-size:12px;font-weight:800;letter-spacing:.1em;color:var(--ui-brand-ink)}.vl-hero h1{font-size:clamp(30px,5vw,50px);margin:6px 0 8px}.vl-hero p{max-width:760px;color:var(--ui-ink-soft);margin:0}.vl-source{display:inline-flex;margin-top:14px;padding:7px 10px;border:1px solid var(--ui-border);border-radius:999px;font-size:12px}
.vl-products{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 20px}.vl-product{display:grid;gap:4px;padding:15px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-surface);text-decoration:none;color:inherit}.vl-product:hover{transform:translateY(-2px);box-shadow:var(--ui-sh-sm)}.vl-product strong{font-size:15px}.vl-product small{color:var(--ui-ink-soft)}
.vl-toolbar{display:flex;gap:10px;align-items:end;margin:0 0 16px;padding:14px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-surface)}.vl-toolbar label{display:grid;gap:4px;font-size:12px;font-weight:700}.vl-toolbar input{min-height:40px;border:1px solid var(--ui-border);border-radius:10px;background:var(--ui-surface);color:var(--ui-ink);padding:0 10px}.vl-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.vl-draw{padding:17px;border:1px solid var(--ui-border);border-radius:18px;background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}.vl-draw-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.vl-draw-head div{display:flex;gap:8px;align-items:baseline}.vl-draw-head small{font-size:10px;color:var(--ui-ink-soft)}.vl-draw-head time{font-size:12px;color:var(--ui-ink-soft)}.vl-result{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.vl-ball{display:inline-grid;place-items:center;min-width:42px;height:42px;padding:0 8px;border-radius:999px;background:var(--ui-brand);color:var(--ui-on-brand);font:800 17px var(--ui-mono)}.vl-ball--bonus{background:var(--ui-special-ink)}.vl-plus{font-weight:900;color:var(--ui-ink-soft)}.vl-jackpots{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px;color:var(--ui-ink-soft);font-size:12px}.vl-jackpots b{color:var(--ui-ink)}.vl-3d{width:100%;display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.vl-3d div{padding:9px;border-radius:10px;background:var(--ui-surface-2)}.vl-3d small{display:block;color:var(--ui-ink-soft);font-size:10px}.vl-3d span{font:700 14px var(--ui-mono)}.vl-bingo-meta{padding-left:8px;color:var(--ui-ink-soft)}.vl-empty{padding:30px;border:1px dashed var(--ui-border);border-radius:18px;text-align:center}
@media(max-width:980px){.vl-products{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.vl-grid,.vl-products{grid-template-columns:1fr}.vl-hero{padding:20px}.vl-toolbar{display:grid}.vl-ball{min-width:38px;height:38px}}
"""

def nav_products(active=""):
 return '<nav class="vl-products" aria-label="Sản phẩm Vietlott">'+''.join(
  f'<a class="vl-product" href="{file}"><strong>{name}</strong><small>{desc}</small></a>'
  for key,(name,file,desc) in PRODUCTS.items())+'</nav>'

def page(product,data,count):
 name,file,desc=PRODUCTS[product]
 empty=("Nguồn đang dùng chưa đăng kết quả sản phẩm này, nên chưa có dữ liệu." if SOURCES[product][1]=="unavailable"
  else "Chưa có dữ liệu đã đồng bộ.")
 cards="".join(card(product,r) for r in data) or f'<div class="vl-empty">{empty}</div>'
 return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{security_meta_tags()}{stylesheet_link()}<title>{name} · Vietlott</title><style>{STYLE}</style></head><body>
 {app_shell_open(file,wide=True)}
 <section class="vl-hero"><span class="vl-kicker">VIETLOTT · KẾT QUẢ</span><h1>{name}</h1><p>Theo dõi kết quả, lịch sử kỳ quay và dữ liệu nền phục vụ phân tích. Kết quả các kỳ đã công bố, lưu theo từng sản phẩm.</p><span class="vl-source">{count:,} kỳ đã lưu</span></section>
 {nav_products(product)}
 <section class="vl-toolbar"><label>Tìm ngày / kỳ quay<input id="vl-search" type="search" placeholder="VD: 2026-10-05 hoặc 00832"></label></section>
 <section class="vl-grid" id="vl-grid">{cards}</section>
 {app_shell_close(file)}
 <script>(()=>{{const q=document.getElementById('vl-search');q.addEventListener('input',()=>{{const s=q.value.trim().toLowerCase();document.querySelectorAll('.vl-draw').forEach(x=>x.hidden=!!s&&!((x.dataset.date+' '+x.dataset.id).toLowerCase().includes(s)));}})}})();</script></body></html>'''

def overview(latest,counts):
 tiles=[]
 for key,(name,file,desc) in PRODUCTS.items():
  r=latest.get(key)
  body=result_markup(key,json.loads(r[2]),r[3],json.loads(r[6] or "{}")) if r else "Chưa đồng bộ"
  tiles.append(f'<a class="vl-draw" href="{file}" style="text-decoration:none;color:inherit"><div class="vl-draw-head"><strong>{name}</strong><small>{counts.get(key,0):,} kỳ</small></div><div class="vl-result">{body}</div></a>')
 return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{security_meta_tags()}{stylesheet_link()}<title>Vietlott · Kết quả</title><style>{STYLE}</style></head><body>
 {app_shell_open("vietlott.html",wide=True)}<section class="vl-hero"><span class="vl-kicker">VIETLOTT · TỔNG QUAN</span><h1>Kết quả Vietlott</h1><p>Một cơ sở dữ liệu riêng cho Lotto 5/35, Mega 6/45, Power 6/55, Max 3D/3D+, Max 3D Pro, Keno và Bingo18. XSMB vẫn là miền ưu tiên của hệ thống.</p><span class="vl-source">Kết quả các kỳ đã công bố</span></section>{nav_products()}<section class="vl-grid">{"".join(tiles)}</section>{app_shell_close("vietlott.html")}</body></html>'''

def build(root):
 """Luôn dựng đủ 8 trang qua write_page; chưa có cơ sở dữ liệu thì in trạng thái trống.

 Trước đây thiếu tệp dữ liệu thì bỏ qua, nên trang trong docs/ là bản giữ chỗ
 viết tay: không khung ứng dụng, không bằng chứng, không điều hướng.
 """
 dbp=root/"data"/"vietlott"/"vietlott.sqlite3";docs=root/"docs";docs.mkdir(exist_ok=True)
 db=sqlite3.connect(dbp) if dbp.exists() else None
 latest={};counts={};history={}
 for p in PRODUCTS:
  counts[p]=db.execute("SELECT COUNT(*) FROM draws WHERE product=?",(p,)).fetchone()[0] if db else 0
  rr=rows(db,p,1) if db else [];latest[p]=rr[0] if rr else None
  history[p]=rows(db,p,160) if db else []
 if db: db.close()
 out=[docs/"vietlott.html"];write_page(out[0],overview(latest,counts))
 for p,(_,file,__) in PRODUCTS.items():
  target=docs/file;write_page(target,page(p,history[p],counts[p]));out.append(target)
 return out
if __name__=="__main__":
 root=Path(__file__).resolve().parents[1]
 for p in build(root):print("đã ghi",p)

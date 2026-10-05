"""Vietlott official-results crawler and analysis database."""
from __future__ import annotations
import argparse,csv,json,re,sqlite3,time
from dataclasses import dataclass,asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BASE="https://vietlott.vn"; TZ=ZoneInfo("Asia/Ho_Chi_Minh")
PRODUCTS={
"lotto535":("Lotto 5/35","/vi/trung-thuong/ket-qua-trung-thuong/535","balls",5,1),
"mega645":("Mega 6/45","/vi/trung-thuong/ket-qua-trung-thuong/645","balls",6,0),
"power655":("Power 6/55","/vi/trung-thuong/ket-qua-trung-thuong/655","balls",6,1),
"max3d":("Max 3D / Max 3D+","/vi/trung-thuong/ket-qua-trung-thuong/max-3D","triples",20,0),
"max3dpro":("Max 3D Pro","/vi/trung-thuong/ket-qua-trung-thuong/max-3DPro","triples",20,0),
"keno":("Keno","/vi/trung-thuong/ket-qua-trung-thuong/view-detail-keno-result","keno",20,0),
"bingo18":("Bingo18","/vi/trung-thuong/ket-qua-trung-thuong/view-detail-bingo18-result","bingo",3,0),
}
UA="VLA/1.0 (+historical lottery research; source vietlott.vn)"

@dataclass(frozen=True)
class Draw:
 product:str; draw_id:str; draw_date:str; result:tuple[str,...]; bonus:str=""
 jackpot_1:int|None=None; jackpot_2:int|None=None; meta_json:str="{}"
 source_url:str=""; fetched_at:str=""

def _date(s):
 m=re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})",s or "")
 return f"{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""

def _header(text):
 m=re.search(r"Kỳ quay thưởng\s*#?(\d+)\s*ngày\s*(\d{1,2}/\d{1,2}/\d{4})",text,re.I)
 if m:return m[1],_date(m[2])
 m=re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s*#(\d+)",text,re.I)
 return (m[2],_date(m[1])) if m else ("","")

def _after(text):
 m=re.search(r"(?:Kỳ quay thưởng\s*#?\d+\s*ngày\s*)?\d{1,2}/\d{1,2}/\d{4}\s*(?:#\d+)?",text,re.I)
 return text[m.end():] if m else text

def _money(text,label):
 m=re.search(label+r"\D{0,100}([\d.]{7,})",text,re.I|re.S)
 return int(re.sub(r"\D","",m[1])) if m else None

def parse_detail(product,html,source_url=""):
 soup=BeautifulSoup(html or "","lxml"); text=soup.get_text("\n",strip=True)
 did,day=_header(text)
 if not did or not day:return None
 kind=PRODUCTS[product][2]; body=_after(text)
 stamp=datetime.now(TZ).isoformat(timespec="seconds")
 if kind=="balls":
  n,bonus=PRODUCTS[product][3],PRODUCTS[product][4]
  head=re.split(r"Các con số dự thưởng|Truyền Hình Trực Tiếp|Giải thưởng",body,1,flags=re.I)[0]
  vals=re.findall(r"(?<!\d)(\d{2})(?!\d)",head)
  if len(vals)<n+bonus:return None
  return Draw(product,did,day,tuple(vals[:n]),vals[n] if bonus else "",
   _money(text,r"(?:Jackpot\s*1|Giải Độc Đắc|Giá trị Jackpot)"),
   _money(text,r"Jackpot\s*2"),"{}",source_url,stamp)
 if kind=="keno":
  head=re.split(r"C\s*CHẴN",body,1,flags=re.I)[0]
  vals=re.findall(r"(?<!\d)(\d{2})(?!\d)",head)
  if len(vals)<20:return None
  vals=vals[:20]; meta={"even":sum(int(x)%2==0 for x in vals),"large":sum(int(x)>40 for x in vals)}
  return Draw(product,did,day,tuple(vals),meta_json=json.dumps(meta),source_url=source_url,fetched_at=stamp)
 if kind=="bingo":
  head=re.split(r"Cửa tổng",body,1,flags=re.I)[0]
  vals=re.findall(r"(?<!\d)([1-6])(?!\d)",head)
  if len(vals)<3:return None
  vals=vals[:3]; total=sum(map(int,vals)); band="Nhỏ" if total<=9 else ("Hòa" if total<=11 else "Lớn")
  return Draw(product,did,day,tuple(vals),meta_json=json.dumps({"sum":total,"band":band},ensure_ascii=False),source_url=source_url,fetched_at=stamp)
 # Max3D: 2 + 4 + 6 + 8 bộ ba theo thứ tự Vietlott công bố.
 head=re.split(r"Các con số dự thưởng",body,1,flags=re.I)[0]
 vals=re.findall(r"(?<!\d)(\d{3})(?!\d)",head)
 if len(vals)<20:
  digits=re.findall(r"(?<!\d)(\d)(?!\d)",head); vals=["".join(digits[i:i+3]) for i in range(0,len(digits)-2,3)]
 if len(vals)<20:return None
 vals=vals[:20]; meta={"special":vals[:2],"first":vals[2:6],"second":vals[6:12],"third":vals[12:20]}
 return Draw(product,did,day,tuple(vals),meta_json=json.dumps(meta,ensure_ascii=False),source_url=source_url,fetched_at=stamp)

def _get(http,url):
 try:
  r=http.get(url,timeout=30,headers={"User-Agent":UA,"Accept-Language":"vi-VN,vi;q=0.9"})
  return (r.text,BeautifulSoup(r.text,"lxml")) if r.status_code==200 and len(r.text)>200 else None
 except requests.RequestException:return None

def _links(soup,product,current=""):
 route=PRODUCTS[product][1].lower(); out=[]
 for a in soup.find_all("a",href=True):
  u=urljoin(BASE,a["href"]); m=re.search(r"[?&]id=(\d+)",u,re.I)
  if route not in u.lower() or not m or m[1]==current:continue
  score=100 if "kỳ trước" in a.get_text(" ",strip=True).lower() else 0
  if current and int(m[1])<int(current):score+=20
  out.append((score,int(m[1]),u))
 return [u for _,__,u in sorted(out,reverse=True)]

def latest_url(http,product):
 direct=urljoin(BASE,PRODUCTS[product][1]); got=_get(http,direct)
 if got:
  d=parse_detail(product,got[0],direct)
  if d:return f"{direct}?id={d.draw_id}&nocatche=1"
  ls=_links(got[1],product)
  if ls:return ls[0]
 for seed in ("/vi/home","/"):
  got=_get(http,urljoin(BASE,seed))
  if got:
   ls=_links(got[1],product)
   if ls:return ls[0]
 return None

def previous_url(soup,product,current):
 ls=_links(soup,product,current.draw_id)
 if ls:return ls[0]
 if PRODUCTS[product][2] in ("balls","triples") and current.draw_id.isdigit() and int(current.draw_id)>1:
  return f"{BASE}{PRODUCTS[product][1]}?id={int(current.draw_id)-1:0{len(current.draw_id)}d}&nocatche=1"
 return None

def init_db(path):
 path.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(path)
 db.executescript("""PRAGMA journal_mode=WAL;
 CREATE TABLE IF NOT EXISTS draws(product TEXT NOT NULL,draw_id TEXT NOT NULL,draw_date TEXT NOT NULL,
 result_json TEXT NOT NULL,bonus TEXT NOT NULL DEFAULT '',jackpot_1 INTEGER,jackpot_2 INTEGER,
 meta_json TEXT NOT NULL DEFAULT '{}',source_url TEXT NOT NULL,fetched_at TEXT NOT NULL,
 PRIMARY KEY(product,draw_id));
 CREATE INDEX IF NOT EXISTS idx_vietlott_product_date ON draws(product,draw_date DESC,draw_id DESC);""")
 return db

def upsert(db,d):
 db.execute("""INSERT INTO draws VALUES(?,?,?,?,?,?,?,?,?,?)
 ON CONFLICT(product,draw_id) DO UPDATE SET draw_date=excluded.draw_date,result_json=excluded.result_json,
 bonus=excluded.bonus,jackpot_1=excluded.jackpot_1,jackpot_2=excluded.jackpot_2,
 meta_json=excluded.meta_json,source_url=excluded.source_url,fetched_at=excluded.fetched_at""",
 (d.product,d.draw_id,d.draw_date,json.dumps(d.result),d.bonus,d.jackpot_1,d.jackpot_2,d.meta_json,d.source_url,d.fetched_at))

def crawl_product(db,http,product,limit=500,delay=.12):
 known={r[0] for r in db.execute("SELECT draw_id FROM draws WHERE product=?",(product,))}
 url=latest_url(http,product); seen=set(); added=0; scanned=0
 while url and url not in seen and scanned<limit:
  seen.add(url); got=_get(http,url)
  if not got:break
  draw=parse_detail(product,got[0],url)
  if not draw:break
  scanned+=1
  if draw.draw_id not in known:upsert(db,draw);known.add(draw.draw_id);added+=1
  nxt=previous_url(got[1],product,draw)
  # Incremental run may stop once it reaches an already persisted chain.
  if draw.draw_id in known and added and nxt:
   m=re.search(r"id=(\d+)",nxt)
   if m and m[1] in known:break
  url=nxt
  if delay:time.sleep(delay)
 db.commit(); return scanned,added

def export(root,db):
 out=root/"data"/"vietlott"; out.mkdir(parents=True,exist_ok=True)
 rows=db.execute("""SELECT product,draw_id,draw_date,result_json,bonus,jackpot_1,jackpot_2,meta_json,source_url,fetched_at
 FROM draws ORDER BY draw_date,product,CAST(draw_id AS INTEGER)""").fetchall()
 fields=("product","draw_id","draw_date","result_json","bonus","jackpot_1","jackpot_2","meta_json","source_url","fetched_at")
 with (out/"draws.csv").open("w",encoding="utf-8",newline="") as f:
  w=csv.writer(f);w.writerow(fields);w.writerows(rows)
 latest={}; counts={}
 for row in rows:
  p=row[0];counts[p]=counts.get(p,0)+1
  latest[p]={"draw_id":row[1],"draw_date":row[2],"result":json.loads(row[3]),"bonus":row[4],"jackpot_1":row[5],"jackpot_2":row[6],"meta":json.loads(row[7]),"source_url":row[8]}
 (out/"latest.json").write_text(json.dumps({"source":"vietlott.vn","timezone":"Asia/Ho_Chi_Minh","counts":counts,"latest":latest},ensure_ascii=False,indent=2),encoding="utf-8")

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--products",default="all");ap.add_argument("--limit",type=int,default=500);ap.add_argument("--delay",type=float,default=.12)
 a=ap.parse_args();root=Path(__file__).resolve().parents[1];db=init_db(root/"data"/"vietlott"/"vietlott.sqlite3");http=requests.Session()
 products=PRODUCTS if a.products=="all" else [x.strip() for x in a.products.split(",") if x.strip()]
 for p in products:
  scanned,added=crawl_product(db,http,p,max(1,a.limit),max(0,a.delay));print(p,scanned,added)
 export(root,db);db.close();return 0
if __name__=="__main__":raise SystemExit(main())

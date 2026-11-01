import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const fixture = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', `
import json,tempfile
from pathlib import Path
import pandas as pd
from jinja2 import Environment,FileSystemLoader
from core.path_models import FIELD_WIDTHS
from pages import build_docs as page
raw=[]
for n in range(12):
 raw.append({'date':f'2026-01-{n+1:02}',**dict.fromkeys(dict(FIELD_WIDTHS),0),'special':int(f'{n%10}{(n+1)%10}123')})
paths=[]
for lag in [1,2]:
 row={'lag':lag,'i':0,'j':1,'p_mean':.4,'p_next':.0123,'max_streak':3,'current_streak':0,'next_day_pred':int(str(raw[12-lag]['special']).zfill(5)[:2])}
 for t in range(2,12):
  d=raw[t]['date']; number=int(str(raw[t-lag]['special']).zfill(5)[:2]); hit=number==int(raw[t]['special'])%100
  row.update({f'{d}_num':number,f'{d}_hit':int(hit),f'{d}_is_de':int(hit)})
 paths.append(row)
picks=pd.DataFrame([{'number':12,'prob':.0123,'support_paths_count':71},{'number':1,'prob':.0123,'support_paths_count':22},{'number':99,'prob':.0123,'support_paths_count':7}])
kwargs=dict(title='Cầu thử',mode='loto',kind='stable',other_link=None,other_kind_label='',other_mode_label='',index_link='index.html',anchor_date='2026-01-12',display_days=10,raw_df=pd.DataFrame(raw))
env=Environment(loader=FileSystemLoader(str(page.TEMPLATES)))
with tempfile.TemporaryDirectory() as tmp:
 out=Path(tmp)/'soi-path-loto-stable.html'
 page._render_page(env,out_path=out,ui_df=pd.DataFrame(paths),picks_df=picks,**kwargs)
 html=out.read_text()
 page._render_page(env,out_path=out,ui_df=pd.DataFrame(),picks_df=pd.DataFrame(),**kwargs)
 print(json.dumps({'html':html,'empty':out.read_text()}))
`], {cwd: fileURLToPath(new URL('../../', import.meta.url)), env:{...process.env,PYTHONPATH:'src'}, encoding:'utf8', maxBuffer:16*1024*1024}));
const override = process.env.APP_PATH_EXPLORER_SCRIPT ? readFileSync(process.env.APP_PATH_EXPLORER_SCRIPT, 'utf8') : null;
async function open(t, query='', empty=false) {
  const dom = new JSDOM(empty ? fixture.empty : fixture.html, {url:`https://example.test/soi-path-loto-stable.html${query}`,runScripts:'outside-only'});
  t.after(()=>dom.window.close());
  const code=[...dom.window.document.querySelectorAll('script:not([src])')].find(s=>s.textContent.includes('window.PathExplorer'));
  dom.window.eval(override ?? code.textContent);
  if(dom.window.document.readyState==='loading') await new Promise(resolve=>dom.window.document.addEventListener('DOMContentLoaded',resolve));
  return dom;
}

test('mở đường đầu hiện nguồn đúng ngày, số 0 đầu và kỳ tới chờ kết quả',async t=>{
  const dom=await open(t);const doc=dom.window.document;
  assert.equal(dom.window.PathExplorer.state.selected,0);
  const cards=doc.querySelectorAll('#path-detail .path-evidence');
  assert.equal(cards.length,11);
  assert.equal(cards[0].dataset.state,'future');
  assert.equal(cards[0].dataset.targetDate,'2026-01-13');
  assert.equal(cards[0].dataset.sourceDate,'2026-01-12');
  assert.equal(cards[0].querySelector('.path-candidate b').textContent,'12');
  assert.equal(cards[2].dataset.targetDate,'2026-01-11');
  assert.equal(cards[2].querySelector('.path-candidate b').textContent,'90');
  assert.deepEqual([...cards[0].querySelectorAll('mark')].map(n=>n.textContent),['1','2']);
  assert.equal(doc.querySelector('[data-path-index="0"]').getAttribute('aria-pressed'),'true');
});

test('chọn nhanh là thao tác thật: lọc theo số dự báo và giữ số 01 trong URL',async t=>{
  const dom=await open(t);const doc=dom.window.document;
  doc.querySelector('[data-path-number="01"]').click();
  assert.equal(dom.window.PathExplorer.state.selected,1);
  assert.equal(doc.querySelector('[data-path-row="0"]').hidden,true);
  assert.equal(doc.querySelector('[data-path-row="1"]').hidden,false);
  assert.equal(doc.querySelector('.path-evidence .path-candidate b').textContent,'01');
  assert.match(doc.querySelector('#path-status').textContent,/1\/2.*01/);
  assert.equal(new URL(dom.window.location.href).searchParams.get('number'),'01');
  doc.querySelector('[data-path-number="99"]').click();
  assert.equal(dom.window.PathExplorer.state.selected,null);
  assert.match(doc.querySelector('#path-detail').textContent,/toàn bộ đường cầu đủ điều kiện/);
  doc.querySelector('#path-reset').click();
  assert.equal(doc.querySelectorAll('[data-path-row]:not([hidden])').length,2);
});

test('liên kết chia sẻ, lựa chọn kỳ gần nhất và nhập hai chữ số hoạt động',async t=>{
  const dom=await open(t,'?number=01&path=L2-%5B0,1%5D');const doc=dom.window.document;
  assert.equal(dom.window.PathExplorer.state.selected,1);
  const days=doc.querySelector('#path-days-filter');days.value='5';days.dispatchEvent(new dom.window.Event('change'));
  assert.equal(doc.querySelectorAll('.path-evidence').length,6);
  assert.equal(doc.querySelectorAll('.path-evidence')[1].dataset.targetDate,'2026-01-12');
  days.value='all';days.dispatchEvent(new dom.window.Event('change'));
  assert.equal(doc.querySelectorAll('.path-evidence').length,11);
  const input=doc.querySelector('#path-number-filter');input.value='0';input.dispatchEvent(new dom.window.Event('input'));
  assert.equal(input.value,'0');
  input.value='01';input.dispatchEvent(new dom.window.Event('input'));
  assert.equal(dom.window.PathExplorer.state.number,'01');
});

test('trang không có cầu giữ trạng thái rỗng và không dựng bộ lọc giả',async t=>{
  const dom=await open(t,'',true);
  assert.equal(dom.window.PathExplorer.state.data.rows.length,0);
  assert.equal(dom.window.document.querySelector('#path-number-filter'),null);
  assert.match(dom.window.document.querySelector('.ui-empty').textContent,/Chưa có dữ liệu/);
});

test('kết quả trúng của chế độ Đặc Biệt không bị gọi là LOTO khi thiếu cờ phụ',async t=>{
  const dom=await open(t);
  const cell={...dom.window.PathExplorer.state.data.rows[0].cells[0],state:'hit'};
  const card=dom.window.PathExplorer.evidenceCard(cell,'de');
  assert.equal(card.dataset.state,'hit-de');
  assert.equal(card.querySelector('.path-outcome strong').textContent,'Về Đặc Biệt');
});

test('chọn đường cầu đưa tiêu điểm và vùng nhìn tới căn cứ vừa cập nhật',async t=>{
  const dom=await open(t);const doc=dom.window.document;
  const calls=[];
  dom.window.HTMLElement.prototype.scrollIntoView=function(options){calls.push({id:this.id,block:options.block});};
  doc.querySelector('[data-path-index="1"]').click();
  assert.equal(doc.activeElement.id,'path-detail-title');
  assert.match(doc.activeElement.textContent,/Đường cầu 2/);
  assert.deepEqual(calls,[{id:'path-detail-title',block:'start'}]);
  doc.querySelector('[data-path-number="12"]').click();
  assert.match(doc.activeElement.textContent,/Đường cầu 1/);
  assert.deepEqual(calls.at(-1),{id:'path-detail-title',block:'start'});
});

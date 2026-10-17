import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const draws = [
  ['2026-09-01','12034'], ['2026-09-02','00012'], ['2026-09-03','90034'],
  ['2026-09-04','10021'], ['2026-09-07','00134'], ['2026-09-08','00000'], ['2026-09-09','00012'],
].map(([d,s], i) => ({d,s,n:[s.slice(-2),...Array(26).fill(i===0 ? '55' : i%2 ? '21':'12')]}));
const build = `import json,sys
from build_stat_pages import PAGES,render_page
draws=json.load(sys.stdin)
print(json.dumps({p.slug:render_page(p,draws,generated="2026-09-09T19:00:00Z") for p in PAGES if p.slug in {"bang-dac-biet","cau-giai-dac-biet","cap-lon-loto","giai-dac-biet-theo-tong"}}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c',build], {
  cwd:fileURLToPath(root),env:{...process.env,PYTHONPATH:'src'},input:JSON.stringify(draws),encoding:'utf8',
}));
const source = readFileSync(new URL('src/templates/stat_pages.js',root),'utf8');
const pairKey = 'sp.pairmarks.v1.';
function setup(t,slug,{storage={},blocked=false}={}) {
  const errors=[];
  const html=process.env.APP_STAT_ENGINE ? pages[slug].replace(source,readFileSync(process.env.APP_STAT_ENGINE,'utf8')) : pages[slug];
  const dom=new JSDOM(html,{
    url:`https://example.test/${slug}.html`,runScripts:'dangerously',pretendToBeVisual:true,
    beforeParse(w) {
      w.addEventListener('error',event=>errors.push(String(event.error)));
      w.ResizeObserver=class {observe(){}};
      if(blocked) Object.defineProperty(w,'localStorage',{get(){throw new Error('blocked');}});
      else for(const [key,value] of Object.entries(storage)) w.localStorage.setItem(key,value);
      w.HTMLElement.prototype.scrollIntoView=function(){};
      w.matchMedia=()=>({matches:false,addEventListener(){}});
    },
  });
  t.after(()=>dom.window.close());
  assert.deepEqual(errors,[]);
  return dom;
}
const cells=(dom,pair)=>[...dom.window.document.querySelectorAll('td.cell[data-key],th.cell[data-key]')]
  .filter(e=>/\|(?:n|c)([0-9]{2}(?:-[0-9]{2})?)(?:\||$)/.exec(e.dataset.key)?.[1]===pair);
function mode(dom,on) {
  const box=dom.window.document.getElementById('sp-pair-mode');
  box.checked=on;
  box.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
}
function change(dom,id,value) {
  const input=dom.window.document.getElementById(id);
  input.value=value;
  input.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
}
function storageEvent(dom,value) {
  const raw=value===null ? null : JSON.stringify(value);
  if(raw===null) dom.window.localStorage.removeItem(pairKey);
  else dom.window.localStorage.setItem(pairKey,raw);
  dom.window.dispatchEvent(new dom.window.StorageEvent('storage',{key:pairKey,newValue:raw,storageArea:dom.window.localStorage}));
}

test('Đặc Biệt: chọn cặp rồi bỏ từ ô đã chọn riêng không để lại dấu bị kẹt',t=>{
  const dom=setup(t,'bang-dac-biet'),same=cells(dom,'34');
  assert.equal(same.length,3);
  same[0].querySelector('b').click();
  assert.equal(same.filter(e=>e.classList.contains('marked')).length,1);
  mode(dom,true);
  same[1].click();
  assert.ok(same.every(e=>e.classList.contains('marked')));
  same[0].click();
  assert.ok(same.every(e=>!e.classList.contains('marked')));
  assert.equal(dom.window.document.querySelectorAll('.marked').length,0);
});

for(const slug of ['bang-dac-biet','cau-giai-dac-biet']) {
  test(`${slug}: đồng bộ cặp từ tab khác, xóa và tải lại không chọn nhầm số thống kê`,t=>{
    const dom=setup(t,slug),d=dom.window.document,same=cells(dom,'12');
    assert.ok(same.length);
    storageEvent(dom,['12']);
    assert.ok(same.every(e=>e.classList.contains('marked')));
    assert.equal(d.querySelectorAll('.marked').length,same.length);
    assert.ok(cells(dom,'21').every(e=>!e.classList.contains('marked')));
    const reloaded=setup(t,slug,{storage:{[pairKey]:dom.window.localStorage.getItem(pairKey)}});
    assert.ok(cells(reloaded,'12').every(e=>e.classList.contains('marked')));
    storageEvent(dom,null);
    assert.equal(d.querySelectorAll('.marked').length,0);
    storageEvent(dom,['00']);
    assert.ok(cells(dom,'00').every(e=>e.classList.contains('marked')));
    const before=[d.getElementById('sp-from').value,d.getElementById('sp-to').value];
    d.getElementById('sp-clear-marks').click();
    assert.equal(d.querySelectorAll('.marked').length,0);
    assert.deepEqual([d.getElementById('sp-from').value,d.getElementById('sp-to').value],before);
  });
  test(`${slug}: storage bị chặn vẫn bật/tắt được cặp đúng hai chữ số`,t=>{
    const dom=setup(t,slug,{blocked:true}),same=cells(dom,'34');
    mode(dom,true);
    same[0].click();
    assert.ok(same.every(e=>e.classList.contains('marked')));
    mode(dom,false);
    assert.ok(same.every(e=>e.classList.contains('marked')));
    same[0].click();
    assert.equal(dom.window.document.querySelectorAll('.marked').length,0);
  });
}

test('Đặc Biệt tuần: dấu ô theo đúng ngày khi lọc sang tuần khác',t=>{
  const dom=setup(t,'bang-dac-biet'),d=dom.window.document;
  const cell=[...d.querySelectorAll('#sp-grid .sp-de')].find(e=>e.textContent.startsWith('00134')).closest('td');
  cell.click();
  change(dom,'sp-from','2026-09-07');
  const same=[...d.querySelectorAll('#sp-grid .sp-de')].find(e=>e.textContent.startsWith('00134')).closest('td');
  assert.ok(same.classList.contains('marked'));
  assert.equal(d.querySelectorAll('.marked').length,1);
});

test('Cầu Đặc Biệt: giữ dấu đúng cặp lộn khi thứ hạng đổi sau lọc',t=>{
  const dom=setup(t,'cau-giai-dac-biet'),d=dom.window.document;
  const cell=cells(dom,'12-21')[0];
  cell.click();
  change(dom,'sp-to','2026-09-03');
  assert.ok(cells(dom,'12-21')[0].classList.contains('marked'));
  assert.equal(d.querySelectorAll('.marked').length,1);
});

test('Khóa dấu ô cũ không gán nhầm sang ngày/số khác, dấu cặp toàn site vẫn giữ',t=>{
  for(const slug of ['bang-dac-biet','cau-giai-dac-biet','cap-lon-loto']) {
    const pair=slug==='cap-lon-loto' ? '12-21' : '12';
    const dom=setup(t,slug,{storage:{
      [`sp.marks.v2.${slug}.html`]:JSON.stringify({cells:['sp-grid:0:1|n34']}),
      [pairKey]:JSON.stringify([pair]),
    }}),d=dom.window.document,same=cells(dom,pair);
    assert.ok(same.length);
    assert.ok(same.every(e=>e.classList.contains('marked')));
    assert.equal(d.querySelectorAll('.marked').length,same.length);
    assert.ok(!d.getElementById('sp-mark-count').textContent.includes('1 ô'));
  }
});

test('Cặp lộn: đủ 45 cặp thật, 10 số kép, đúng lượt và giữ dấu khi xếp lại theo bộ lọc',t=>{
  const dom=setup(t,'cap-lon-loto'),d=dom.window.document;
  const pairRows=[...d.querySelectorAll('#sp-grid tbody tr')];
  assert.equal(pairRows.length,45);
  assert.equal(d.querySelectorAll('#sp-kep tbody tr').length,10);
  const row=pairRows.find(row=>row.cells[1].textContent==='12 ↔ 21');
  const expected=draws.flatMap(r=>r.n);
  assert.equal(Number(row.cells[2].textContent),expected.filter(x=>x==='12').length);
  assert.equal(Number(row.cells[3].textContent),expected.filter(x=>x==='21').length);
  assert.equal(Number(row.cells[4].textContent),expected.filter(x=>x==='12'||x==='21').length);
  const target=cells(dom,'00')[0];
  target.click();
  change(dom,'sp-from','2026-09-08');
  assert.ok(cells(dom,'00')[0].classList.contains('marked'));
  assert.equal(d.querySelectorAll('.marked').length,1);
});

test('Theo tổng: giữ đúng số lượt, gan, chuyển tiếp liền ngày và chẵn lẻ sau khi chia lại bảng',t=>{
  const dom=setup(t,'giai-dac-biet-theo-tong'),d=dom.window.document;
  const total=s=>[...s.slice(-2)].reduce((sum,v)=>sum+Number(v),0)%10;
  const hits=Array(10).fill(0),last=Array(10).fill(-1);
  const trans=Array.from({length:10},()=>Array(10).fill(0)),from=Array(10).fill(0);
  draws.forEach((draw,i)=>{const n=total(draw.s);hits[n]++;last[n]=i;});
  for(let i=1;i<draws.length;i++) if((Date.parse(draws[i].d)-Date.parse(draws[i-1].d))/86400000===1) {
    const a=total(draws[i-1].s),b=total(draws[i].s);trans[a][b]++;from[a]++;
  }
  for(const row of d.querySelectorAll('#sp-grid tbody tr')) {
    const n=Number(row.cells[0].textContent);
    assert.equal(row.cells[1].textContent,last[n]<0 ? '—' : draws[last[n]].d);
    assert.equal(Number(row.cells[2].textContent),last[n]<0 ? draws.length : draws.length-1-last[n]);
    assert.equal(Number(row.cells[3].textContent),hits[n]);
  }
  const transitions=[...d.querySelectorAll('#sp-trans tbody tr')];
  assert.equal(transitions.length,Math.min(40,from.filter(Boolean).length*10));
  for(const row of transitions) {
    const a=Number(row.cells[0].textContent),b=Number(row.cells[1].textContent);
    assert.equal(Number(row.cells[2].textContent),trans[a][b]);
    assert.equal(Number(row.cells[3].textContent),from[a]);
    assert.equal(row.cells[4].textContent,(100*trans[a][b]/from[a]).toFixed(2).replace('.',',')+' %');
  }
  assert.equal(d.querySelectorAll('#sp-parity tbody tr').length,from.filter(Boolean).length);
  for(const row of d.querySelectorAll('#sp-parity tbody tr')) {
    const a=Number(row.cells[0].textContent),even=trans[a].filter((_,i)=>i%2===0).reduce((sum,v)=>sum+v,0);
    assert.equal(Number(row.cells[1].textContent),from[a]);
    assert.equal(row.cells[2].textContent,(100*even/from[a]).toFixed(2).replace('.',',')+' %');
  }
  change(dom,'sp-from','2026-10-01');
  for(const id of ['sp-grid','sp-trans','sp-parity']) {
    assert.equal(d.querySelectorAll(`#${id} tbody .sp-empty-row`).length,1);
    assert.equal(d.querySelectorAll(`#${id} colgroup`).length,1);
  }
});

import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM, VirtualConsole} from 'jsdom';

const root=new URL('../../',import.meta.url);
const fixtures={history:[
 {d:'2025-12-31',s:'00032'}, {d:'2026-01-01',s:'00003'},
 {d:'2026-01-02',s:'10032'}, {d:'2026-01-04',s:'45032'},
 {d:'2026-01-05',s:'12309'}, {d:'2026-01-06',s:'45932'},
],empty:[],withoutLoto:[
 {d:'2026-04-01',s:'00032',n:[]}, {d:'2026-04-02',s:'00003',n:[]},
],invalidLoto:[{d:'2026-05-01',s:'00032',n:['',null,' ',0,'01',NaN,'100']}]};
fixtures.history.forEach((row,index)=>{
 row.n=['00','00','01','99',...Array.from({length:23},(_,i)=>String((index*11+i*3+2)%100).padStart(2,'0'))];
});
const python=`import json,sys\nfrom pages.build_stat_pages import PAGES,render_page\np=next(p for p in PAGES if p.slug=='giai-db-ngay-mai')\nprint(json.dumps({k:render_page(p,v,generated='2026-01-06T20:00:00Z') for k,v in json.load(sys.stdin).items()}))`;
const engineSource=readFileSync(new URL('src/web/templates/stat_pages.js',root),'utf8');
const pages=JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON||'python3',['-c',python],{
 cwd:fileURLToPath(root),env:{...process.env,PYTHONPATH:'src'},input:JSON.stringify(fixtures),encoding:'utf8',maxBuffer:8*1024*1024,
}));
function setup(t,fixture='history',query=''){
 const errors=[];const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
 const markup=process.env.APP_STAT_ENGINE ? pages[fixture].replace(engineSource,readFileSync(process.env.APP_STAT_ENGINE,'utf8')) : pages[fixture];
 const dom=new JSDOM(markup,{runScripts:'dangerously',url:'https://example.test/giai-db-ngay-mai.html'+query,virtualConsole:console});
 t.after(()=>{assert.deepEqual(errors,[]);dom.window.close();});return dom;
}
function choose(dom,value){const s=dom.window.document.getElementById('sp-tomorrow-number');assert.ok(s,'Thiếu bộ chọn 00–99');s.value=value;s.dispatchEvent(new dom.window.Event('change',{bubbles:true}));}
function range(dom,from,to){
 // Trang dùng mốc nhanh; thêm đầu vào cho hợp đồng tra ngày ngoài dải của bộ máy chung.
 for(const [id,value] of [['sp-from',from],['sp-to',to]]){
  const input=dom.window.document.createElement('input');input.id=id;input.type='date';input.value=value;
  dom.window.document.querySelector('.app-tomorrow-controls').append(input);
 }
 choose(dom,'32');
}
const rows=dom=>[...dom.window.document.querySelectorAll('#sp-grid tbody tr[data-trigger-date]')];
const expectedLoto=row=>[...new Set(row.n)].sort().map(number=>[number,row.n.filter(n=>n===number).length]);
function actualLoto(row,kind){
 const cell=row.querySelector(`[data-${kind}-loto]`);
 assert.ok(cell,`Thiếu LOTO ${kind}`);
 return [...cell.querySelectorAll('[data-loto-number]')].map(chip=>[chip.dataset.lotoNumber,Number(chip.dataset.lotoCount)]);
}

test('same special suffix is one column, newest first; exact following calendar date only',t=>{
 const dom=setup(t);const doc=dom.window.document;
 assert.equal(doc.querySelector('#sp-tomorrow-number')?.value,'32');
 assert.deepEqual(rows(dom).map(r=>r.dataset.triggerDate),['2026-01-06','2026-01-04','2026-01-02','2025-12-31']);
 assert.deepEqual(rows(dom).map(r=>r.querySelector('[data-trigger-special]').textContent.trim()),['45932','45032','10032','00032']);
 assert.deepEqual(rows(dom).map(r=>r.querySelector('[data-next-special]')?.textContent.trim()??null),[null,'12309',null,'00003']);
 assert.match(rows(dom)[0].textContent,/Chờ kết quả/);
 assert.match(rows(dom)[2].textContent,/Chưa có dữ liệu/);
 assert.equal(doc.querySelectorAll('#sp-tomorrow-frequencies [data-count]').length,2);
 assert.equal(doc.querySelector('#sp-tomorrow-frequencies [data-number="03"]').dataset.count,'1');
 assert.match(doc.querySelector('#sp-tomorrow-summary').textContent,/4 lần/);
 assert.match(doc.querySelector('#sp-tomorrow-summary').textContent,/2 lần có kết quả/);
 assert.doesNotMatch(doc.querySelector('#sp-grid').textContent,/Chưa về \/ chu kỳ|Điểm|Hạng/);
});

test('leading zeros, query selection and changing number update actual historical results',t=>{
 const dom=setup(t,'history','?number=03');
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-number')?.value,'03');
 assert.equal(rows(dom).length,1);
 assert.equal(rows(dom)[0].querySelector('[data-trigger-special]').textContent,'00003');
 assert.equal(rows(dom)[0].querySelector('[data-next-special]').textContent,'10032');
 choose(dom,'99');
 assert.equal(rows(dom).length,0);
 assert.match(dom.window.document.querySelector('#sp-grid').textContent,/Chưa có lần/);
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-frequencies').children.length,0);
 choose(dom,'32');
 assert.equal(rows(dom).length,4);
 assert.equal(dom.window.document.querySelectorAll('#sp-grid td [title]').length,0);
});

test('LOTO is beside each full special and preserves all 27 endings from the exact same date',t=>{
 const dom=setup(t),history=rows(dom),byDate=new Map(fixtures.history.map(row=>[row.d,row]));
 for(const row of history){
  assert.equal(row.cells.length,5);
  const source=byDate.get(row.dataset.triggerDate);
  assert.deepEqual(actualLoto(row,'trigger'),expectedLoto(source));
  assert.equal(row.cells[1].querySelector('[data-trigger-special]').textContent,source.s);
  assert.ok(row.cells[2].querySelector('[data-trigger-loto]'));
  assert.equal(row.querySelector('[data-trigger-loto]').dataset.lotoDate,source.d);
  assert.equal(actualLoto(row,'trigger').reduce((total,[,count])=>total+count,0),27);
  assert.equal(row.querySelector('[data-trigger-loto] [data-loto-number="00"]').dataset.lotoCount,String(source.n.filter(n=>n==='00').length));
  assert.match(row.querySelector('[data-trigger-loto] [data-loto-number="00"]').textContent,/×2/);
  const [year,month,day]=source.d.split('-').map(Number);
  const nextDate=new Date(Date.UTC(year,month-1,day+1)).toISOString().slice(0,10),next=byDate.get(nextDate);
  assert.equal(row.querySelector('[data-next-date]').dataset.nextDate,nextDate);
  assert.match(row.cells[3].textContent,new RegExp(nextDate.split('-').reverse().join('/')));
  assert.ok(row.cells[4].querySelector('[data-next-loto]'));
  if(next){
   assert.equal(row.cells[3].querySelector('[data-next-special]').textContent,next.s);
   assert.deepEqual(actualLoto(row,'next'),expectedLoto(next));
   assert.equal(row.querySelector('[data-next-loto]').dataset.lotoDate,next.d);
   assert.equal(actualLoto(row,'next').reduce((total,[,count])=>total+count,0),27);
  }else assert.deepEqual(actualLoto(row,'next'),[]);
 }
 assert.deepEqual([...dom.window.document.querySelectorAll('#sp-tomorrow-frequencies [data-count]')].map(c=>[c.dataset.number,c.dataset.count]),[['03','1'],['09','1']]);
 choose(dom,'03');
 assert.deepEqual(actualLoto(rows(dom)[0],'trigger'),expectedLoto(byDate.get('2026-01-01')));
 assert.deepEqual(actualLoto(rows(dom)[0],'next'),expectedLoto(byDate.get('2026-01-02')));
 assert.equal(dom.window.document.querySelectorAll('#sp-grid [title]').length,0);
});

test('range filters source occurrences while tomorrow LOTO still looks up the full calendar history',t=>{
 const dom=setup(t);range(dom,'2025-12-31','2025-12-31');
 assert.deepEqual(rows(dom).map(r=>r.dataset.triggerDate),['2025-12-31']);
 assert.deepEqual(actualLoto(rows(dom)[0],'next'),expectedLoto(fixtures.history[1]));
 assert.equal(rows(dom)[0].querySelector('[data-next-special]').textContent,'00003');
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-frequencies [data-number="03"]').dataset.count,'1');
});

test('missing LOTO data does not invent endings and does not change special-suffix frequencies',t=>{
 const dom=setup(t,'withoutLoto','?number=32'),row=rows(dom)[0];
 assert.deepEqual(actualLoto(row,'trigger'),[]);assert.deepEqual(actualLoto(row,'next'),[]);
 assert.match(row.querySelector('[data-trigger-loto]').textContent,/Chưa có dữ liệu LOTO/);
 assert.match(row.querySelector('[data-next-loto]').textContent,/Chưa có dữ liệu LOTO/);
 assert.equal(row.querySelector('[data-next-special]').textContent,'00003');
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-frequencies [data-number="03"]').dataset.count,'1');
});

test('invalid LOTO entries stay missing while numeric zero keeps its two digits',t=>{
 const dom=setup(t,'invalidLoto','?number=32'),row=rows(dom)[0];
 assert.deepEqual(actualLoto(row,'trigger'),[['00',1],['01',1]]);
 assert.match(row.querySelector('[data-trigger-loto]').textContent,/2 lượt/);
});

test('LOTO clicks keep DB marks independent and DB pair marks still follow the same suffix',t=>{
 const dom=setup(t),doc=dom.window.document,first=rows(dom)[0];
 const triggerCell=first.querySelector('[data-trigger-special]').closest('td');
 const lotoCell=first.querySelector('[data-trigger-loto]').closest('td');
 assert.match(triggerCell.dataset.key,/:1\|n32$/);
 const nextCell=rows(dom).at(-1).querySelector('[data-next-special]').closest('td');
 assert.match(nextCell.dataset.key,/:2\|n03$/);
 first.querySelector('[data-trigger-loto] [data-loto-number="00"]').click();
 assert.ok(lotoCell.classList.contains('marked'));assert.ok(!triggerCell.classList.contains('marked'));
 doc.querySelector('#sp-clear-marks').click();
 doc.querySelector('#sp-pair-mode').checked=true;
 first.querySelector('[data-trigger-special]').click();
 assert.ok(rows(dom).every(row=>row.querySelector('[data-trigger-special]').closest('td').classList.contains('marked')));
 assert.ok(rows(dom).every(row=>!row.querySelector('[data-trigger-loto]').closest('td').classList.contains('marked')));
 choose(dom,'03');choose(dom,'32');
 assert.ok(rows(dom).every(row=>row.querySelector('[data-trigger-special]').closest('td').classList.contains('marked')));
 rows(dom)[0].querySelector('[data-trigger-special]').click();
 assert.equal(doc.querySelectorAll('#sp-grid .marked').length,0);
 rows(dom).at(-1).querySelector('[data-next-special]').click();
 assert.ok(rows(dom).at(-1).querySelector('[data-next-special]').closest('td').classList.contains('marked'));
 assert.ok(!rows(dom).at(-1).querySelector('[data-next-loto]').closest('td').classList.contains('marked'));
 choose(dom,'03');
 assert.ok(rows(dom)[0].querySelector('[data-trigger-special]').closest('td').classList.contains('marked'));
});

test('empty history stays empty and latest-number shortcut restores actual latest suffix',t=>{
 const empty=setup(t,'empty');
 choose(empty,'32');assert.equal(rows(empty).length,0);
 assert.doesNotMatch(empty.window.document.querySelector('.app-tomorrow-shell').textContent,/NaN|undefined|Infinity/);
 const dom=setup(t);choose(dom,'03');
 dom.window.document.querySelector('#sp-tomorrow-latest').click();
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-number').value,'32');
 assert.equal(rows(dom).length,4);
});

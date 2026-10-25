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
],empty:[]};
for(const rows of Object.values(fixtures)) for(const row of rows) row.n=Array(27).fill(row.s.slice(-2));
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
const rows=dom=>[...dom.window.document.querySelectorAll('#sp-grid tbody tr[data-trigger-date]')];

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

test('empty history stays empty and latest-number shortcut restores actual latest suffix',t=>{
 const empty=setup(t,'empty');
 choose(empty,'32');assert.equal(rows(empty).length,0);
 assert.doesNotMatch(empty.window.document.querySelector('.app-tomorrow-shell').textContent,/NaN|undefined|Infinity/);
 const dom=setup(t);choose(dom,'03');
 dom.window.document.querySelector('#sp-tomorrow-latest').click();
 assert.equal(dom.window.document.querySelector('#sp-tomorrow-number').value,'32');
 assert.equal(rows(dom).length,4);
});

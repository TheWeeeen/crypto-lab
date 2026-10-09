/* crypto-lab — интерфейс: график, рисование, проверка гипотез.
   Без внешних библиотек: чистый canvas. */
'use strict';

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const PAD = { l: 10, r: 66, t: 12, b: 24 };
const COL = { up:'#26a69a', dn:'#ef5350', grid:'#1b212a', axis:'#7d8896',
              acc:'#2962ff', warn:'#f0b90b', txt:'#d6dce5', muted:'#7d8896',
              level:'#f0b90b', trend:'#26a69a', res:'#ef5350', fib:'#8e7cc3' };

const S = {
  bars: [], symbol:'BTCUSDT', interval:'1d', limit:1000,
  view:{i0:0, i1:100},
  tool:'cursor', drawings:[], selected:null, draft:null, nextId:1,
  overlays:{levels:[], trendlines:[], patterns:[]},
  result:null, tab:'table', lastRows:null, hover:null, drag:null, strategies:[],
};
/* код доступа держим ещё и в памяти: если браузер запрещает хранить данные сайта,
   вход всё равно работает до закрытия вкладки */
let MEM_TOKEN = null;

/* ---------- утилиты ---------- */
const clamp = (v,a,b)=>Math.max(a,Math.min(b,v));
const fmt = (v,d=2)=>(v===null||v===undefined||!isFinite(v))?'—':Number(v).toFixed(d);
const pct = (v,d=1)=>(v===null||!isFinite(v))?'—':(v*100).toFixed(d)+'%';
const money = (v,cur='₽')=>{
  if(v===null||!isFinite(v)) return '—';
  const a=Math.abs(v);
  return (v<0?'−':'')+a.toLocaleString('ru-RU',{maximumFractionDigits:0})+' '+cur;
};
const dt = t => { const d=new Date(t); return d.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit',year:'2-digit'}); };
const cls = v => v>0?'pos':(v<0?'neg':'');

async function api(path, params={}, body=null){
  const u = new URL(path, location.href);
  Object.entries(params).forEach(([k,v])=>{ if(v!==null&&v!==undefined&&v!=='') u.searchParams.set(k,v); });
  if(!u.searchParams.get('token')){
    let t = MEM_TOKEN;
    if(!t){ try{ t = localStorage.getItem('lab_token'); }catch(e){} }
    if(!t){ try{ t = new URL(location.href).searchParams.get('token'); }catch(e){} }
    if(t) u.searchParams.set('token', t);
  }
  const opt = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {};
  const r = await fetch(u, opt);
  if(r.status === 401){ showGate(); throw new Error('нужен код доступа'); }
  const j = await r.json();
  if(j.error) throw new Error(j.error);
  return j;
}

function busy(on, text='считаю…'){
  $('#loading').textContent = text;
  $('#loading').classList.toggle('hidden', !on);
}
function setStatus(t){ $('#status').textContent = t || ''; }

/* ---------- геометрия графика ---------- */
const cvs = () => $('#chart');
function plotSize(){
  const c = cvs();
  return { W:c.clientWidth, H:c.clientHeight,
           pw:Math.max(10,c.clientWidth-PAD.l-PAD.r), ph:Math.max(10,c.clientHeight-PAD.t-PAD.b) };
}
function visibleBars(){
  const {i0,i1} = S.view;
  const a = clamp(Math.floor(i0),0,S.bars.length-1), b = clamp(Math.ceil(i1),0,S.bars.length-1);
  return S.bars.slice(a,b+1);
}
function priceRange(){
  const vb = visibleBars(); if(!vb.length) return {lo:0,hi:1};
  let lo=Infinity, hi=-Infinity;
  for(const b of vb){ lo=Math.min(lo,b.l); hi=Math.max(hi,b.h); }
  const pad = (hi-lo)*0.06 || 1;
  return {lo:lo-pad, hi:hi+pad};
}
function X(i){ const {pw}=plotSize(); const {i0,i1}=S.view;
  return PAD.l + (i-i0)/Math.max(1e-9,i1-i0)*pw; }
function IX(x){ const {pw}=plotSize(); const {i0,i1}=S.view;
  return i0 + (x-PAD.l)/pw*(i1-i0); }
function Y(p){ const {ph}=plotSize(); const {lo,hi}=priceRange();
  return PAD.t + (hi-p)/Math.max(1e-9,hi-lo)*ph; }
function PY(y){ const {ph}=plotSize(); const {lo,hi}=priceRange();
  return hi - (y-PAD.t)/ph*(hi-lo); }

/* ---------- рендер ---------- */
function fitCanvas(c){
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if(c.width !== Math.round(w*dpr) || c.height !== Math.round(h*dpr)){
    c.width = Math.round(w*dpr); c.height = Math.round(h*dpr);
  }
  const g = c.getContext('2d');
  g.setTransform(dpr,0,0,dpr,0,0);
  return g;
}

function render(){
  const c = cvs(); const g = fitCanvas(c);
  const {W,H,pw,ph} = plotSize();
  g.clearRect(0,0,W,H);
  g.fillStyle = '#0a0d11'; g.fillRect(0,0,W,H);
  if(!S.bars.length){ g.fillStyle=COL.muted; g.font='13px sans-serif';
    g.fillText('Загрузи данные: выбери монету и нажми «Загрузить»', 20, 34); return; }

  const {lo,hi} = priceRange();

  // сетка + ось цен
  g.font = '10px ui-monospace, monospace'; g.textBaseline = 'middle';
  const steps = 6;
  for(let k=0;k<=steps;k++){
    const p = lo + (hi-lo)*k/steps, y = Y(p);
    g.strokeStyle = COL.grid; g.beginPath(); g.moveTo(PAD.l,y); g.lineTo(PAD.l+pw,y); g.stroke();
    g.fillStyle = COL.axis; g.textAlign='left';
    g.fillText(p>=1000?p.toFixed(0):p.toFixed(p<10?3:2), PAD.l+pw+6, y);
  }

  // свечи
  const nVis = Math.max(1, S.view.i1 - S.view.i0);
  const bw = Math.max(1, Math.min(16, pw/nVis*0.68));
  const volTop = PAD.t + ph*0.8, volH = ph*0.18;
  let vmax = 0; for(const b of visibleBars()) vmax = Math.max(vmax, b.v);

  const a = Math.max(0, Math.floor(S.view.i0)-1), b = Math.min(S.bars.length-1, Math.ceil(S.view.i1)+1);
  for(let i=a;i<=b;i++){
    const bar = S.bars[i], x = X(i), up = bar.c >= bar.o;
    g.strokeStyle = g.fillStyle = up?COL.up:COL.dn;
    g.beginPath(); g.moveTo(x, Y(bar.h)); g.lineTo(x, Y(bar.l)); g.stroke();
    const y1 = Y(Math.max(bar.o,bar.c)), y2 = Y(Math.min(bar.o,bar.c));
    g.fillRect(x-bw/2, y1, bw, Math.max(1, y2-y1));
    if(vmax>0 && bw>=1.5){
      g.globalAlpha = .35;
      g.fillRect(x-bw/2, volTop+volH*(1-bar.v/vmax), bw, volH*bar.v/vmax);
      g.globalAlpha = 1;
    }
  }

  // ось времени
  g.fillStyle = COL.axis; g.textAlign='center';
  const labelEvery = Math.max(1, Math.ceil(nVis/8));
  for(let i=Math.ceil(S.view.i0); i<=S.view.i1; i+=labelEvery){
    if(i<0||i>=S.bars.length) continue;
    g.fillText(dt(S.bars[i].t), X(i), PAD.t+ph+13);
  }

  // оверлеи автопоиска
  drawLevels(g); drawTrendlines(g); drawPatterns(g);

  // метки сделок результата
  drawTrades(g);

  // рисунки пользователя
  for(const d of S.drawings) drawObj(g, d, d===S.selected);
  if(S.draft) drawObj(g, S.draft, true);

  // кроссхэйр
  if(S.hover && !S.drag){
    const {x,y} = S.hover;
    if(x>PAD.l && x<PAD.l+pw && y>PAD.t && y<PAD.t+ph){
      g.strokeStyle='#39424f'; g.setLineDash([3,3]);
      g.beginPath(); g.moveTo(x,PAD.t); g.lineTo(x,PAD.t+ph);
      g.moveTo(PAD.l,y); g.lineTo(PAD.l+pw,y); g.stroke(); g.setLineDash([]);
      g.fillStyle='#1c222c'; g.fillRect(PAD.l+pw, y-8, 62, 16);
      g.fillStyle=COL.txt; g.textAlign='left';
      g.fillText(PY(y).toFixed(PY(y)<10?3:2), PAD.l+pw+5, y);
    }
  }
  drawHud();
}

function drawHud(){
  const i = S.hover ? clamp(Math.round(IX(S.hover.x)),0,S.bars.length-1) : S.bars.length-1;
  const b = S.bars[i]; if(!b) return;
  const chg = b.o ? (b.c/b.o-1) : 0;
  $('#hud').innerHTML =
    `<b>${S.symbol}</b> ${S.interval} · бар ${i+1}/${S.bars.length} · ${dt(b.t)}<br>` +
    `O ${fmt(b.o,2)}  H ${fmt(b.h,2)}  L ${fmt(b.l,2)}  C <b class="${cls(chg)}">${fmt(b.c,2)}</b>  ` +
    `<span class="${cls(chg)}">${pct(chg,2)}</span>  V ${(b.v/1000).toFixed(1)}k`;
}

function drawLevels(g){
  const {pw} = plotSize();
  for(const l of S.overlays.levels){
    const y = Y(l.price); if(y<PAD.t||y>PAD.t+plotSize().ph) continue;
    g.strokeStyle = COL.level; g.globalAlpha=.75; g.setLineDash([6,4]);
    g.beginPath(); g.moveTo(PAD.l,y); g.lineTo(PAD.l+pw,y); g.stroke();
    g.setLineDash([]); g.globalAlpha=1;
    g.fillStyle=COL.level; g.font='10px ui-monospace,monospace'; g.textAlign='right';
    const lab = `${l.price.toFixed(0)} · ${l.touches} кас · p=${fmt(l.p_value,2)}`;
    g.fillText(lab, PAD.l+pw-4, y-4);
  }
}
function drawTrendlines(g){
  const {pw}=plotSize();
  for(const t of S.overlays.trendlines){
    const i1=t.i1, i2=t.i2;
    const k = (t.p2-t.p1)/Math.max(1,(i2-i1));
    const x1=X(i1), x2=PAD.l+pw;
    const y1=Y(t.p1), y2=Y(t.p1 + k*(IX(x2)-i1));
    g.strokeStyle = t.kind==='support'?COL.trend:COL.res; g.globalAlpha=.6;
    g.beginPath(); g.moveTo(x1,y1); g.lineTo(x2,y2); g.stroke(); g.globalAlpha=1;
  }
}
function drawPatterns(g){
  for(const p of S.overlays.patterns){
    if(p.i1===undefined||p.i2===undefined) continue;
    const x1=X(p.i1), x2=X(p.i2), y=Y(p.price||0);
    const bottom = /основан/.test(p.name||'');
    g.strokeStyle = bottom?COL.up:COL.dn;
    g.globalAlpha=.5; g.setLineDash([2,3]);
    g.beginPath(); g.moveTo(x1,y); g.lineTo(x2,y); g.stroke();
    g.setLineDash([]); g.globalAlpha=1;
  }
}

function drawTrades(g){
  const r = S.result; if(!r || !r.trades || !r.bars || r.bars.length !== S.bars.length) return;
  for(const t of r.trades){
    const i = S.bars.findIndex(b=>b.t===t.entry_t); if(i<0) continue;
    const x = X(i), y = Y(t.entry_px);
    g.fillStyle = t.side==='long'?COL.up:COL.dn;
    g.beginPath();
    if(t.side==='long'){ g.moveTo(x,y+14); g.lineTo(x-5,y+22); g.lineTo(x+5,y+22); }
    else { g.moveTo(x,y-14); g.lineTo(x-5,y-22); g.lineTo(x+5,y-22); }
    g.closePath(); g.fill();
    if(t.exit_t){ const j=S.bars.findIndex(b=>b.t===t.exit_t);
      if(j>=0){ const xe=X(j), ye=Y(t.exit_px);
        g.strokeStyle = t.pnl>0?COL.up:COL.dn; g.globalAlpha=.5;
        g.beginPath(); g.moveTo(x,y); g.lineTo(xe,ye); g.stroke(); g.globalAlpha=1; } }
  }
}

/* ---------- рисование объектов ---------- */
const OBJ_LABEL = { hline:'Уровень', trend:'Трендлайн', rect:'Зона', fib:'Фибоначчи', vline:'Метка' };
function objColor(d){
  if(d.type==='hline') return COL.level;
  if(d.type==='trend') return COL.trend;
  if(d.type==='rect') return COL.acc;
  if(d.type==='fib') return COL.fib;
  return COL.muted;
}
function drawObj(g, d, sel){
  const {pw,ph}=plotSize();
  g.strokeStyle = objColor(d); g.fillStyle = objColor(d);
  g.lineWidth = sel?2:1.3;
  if(d.type==='hline'){
    const y=Y(d.p1);
    g.beginPath(); g.moveTo(PAD.l,y); g.lineTo(PAD.l+pw,y); g.stroke();
    g.font='10px ui-monospace,monospace'; g.textAlign='left';
    g.fillText(`${d.p1.toFixed(2)}`, PAD.l+4, y-4);
  } else if(d.type==='vline'){
    const x=X(d.i1);
    g.setLineDash([4,4]); g.beginPath(); g.moveTo(x,PAD.t); g.lineTo(x,PAD.t+ph); g.stroke(); g.setLineDash([]);
  } else if(d.type==='trend' || d.type==='fib'){
    const x1=X(d.i1),y1=Y(d.p1),x2=X(d.i2),y2=Y(d.p2);
    g.beginPath(); g.moveTo(x1,y1); g.lineTo(x2,y2); g.stroke();
    if(d.type==='fib'){
      const ratios=[0,0.236,0.382,0.5,0.618,0.786,1];
      g.font='9px ui-monospace,monospace'; g.textAlign='left';
      for(const r of ratios){
        const p = d.p2 + (d.p1-d.p2)*r, y=Y(p);
        g.globalAlpha=.5; g.setLineDash([2,3]);
        g.beginPath(); g.moveTo(PAD.l,y); g.lineTo(PAD.l+pw,y); g.stroke();
        g.setLineDash([]); g.globalAlpha=.9;
        g.fillText(`${(r*100).toFixed(1)}% ${p.toFixed(2)}`, PAD.l+4, y-3);
        g.globalAlpha=1;
      }
    }
    for(const [x,y] of [[x1,y1],[x2,y2]]){ g.beginPath(); g.arc(x,y,3,0,7); g.fill(); }
  } else if(d.type==='rect'){
    const x1=X(d.i1),x2=X(d.i2),y1=Y(d.p1),y2=Y(d.p2);
    g.globalAlpha=.12; g.fillRect(Math.min(x1,x2),Math.min(y1,y2),Math.abs(x2-x1),Math.abs(y2-y1));
    g.globalAlpha=.9; g.strokeRect(Math.min(x1,x2),Math.min(y1,y2),Math.abs(x2-x1),Math.abs(y2-y1));
    g.globalAlpha=1;
  }
  g.lineWidth=1;
  if(sel && d.i1!==undefined){
    for(const [x,y] of objHandles(d)){ g.fillStyle='#fff';
      g.beginPath(); g.arc(x,y,4,0,7); g.fill(); }
  }
}
function objHandles(d){
  if(d.type==='hline') return [[PAD.l+plotSize().pw/2, Y(d.p1)]];
  if(d.type==='vline') return [[X(d.i1), PAD.t+plotSize().ph/2]];
  return [[X(d.i1),Y(d.p1)],[X(d.i2),Y(d.p2)]];
}

/* ---------- взаимодействие ---------- */
function bindChart(){
  if(S._chartBound) return;   /* повторный вход не должен навешивать обработчики дважды */
  S._chartBound = true;
  const c = cvs();
  c.addEventListener('pointermove', e=>{
    const r=c.getBoundingClientRect();
    const x=e.clientX-r.left, y=e.clientY-r.top;
    if(S.drag){
      if(S.drag.mode==='pan'){
        const {pw}=plotSize();
        const per = (S.view.i1-S.view.i0)/pw;
        const d = (S.drag.x-x)*per;
        S.view.i0 += d; S.view.i1 += d;
        clampView();
      } else if(S.drag.mode==='draw' && S.draft){
        const d=S.draft;
        if(d.type==='hline'){ d.p1=PY(y); }
        else if(d.type==='vline'){ d.i1=IX(x); }
        else { d.i2=IX(x); d.p2=PY(y); }
      } else if(S.drag.mode==='move' && S.selected){
        const d=S.selected;
        if(d.type==='hline') d.p1=PY(y);
        else if(d.type==='vline') d.i1=IX(x);
        else {
          const di=IX(x)-S.drag.ix, dp=PY(y)-S.drag.py;
          d.i1+=di; d.i2+=di; d.p1+=dp; d.p2+=dp;
          S.drag.ix=IX(x); S.drag.py=PY(y);
        }
      }
      render(); return;
    }
    S.hover={x,y}; render();
  });
  c.addEventListener('pointerdown', e=>{
    const r=c.getBoundingClientRect(), x=e.clientX-r.left, y=e.clientY-r.top;
    if(S.tool==='cursor'){
      const hit = hitTest(x,y);
      if(hit){ S.selected=hit; S.drag={mode:'move', x, y, ix:IX(x), py:PY(y)}; }
      else { S.drag={mode:'pan', x, y}; }
      renderDrawList(); return;
    }
    const p1=PY(y), i1=IX(x);
    S.draft = { id:S.nextId++, type:S.tool, i1, p1, i2:i1, p2:p1,
                label:OBJ_LABEL[S.tool] };
    S.drag={mode:'draw', x, y};
  });
  window.addEventListener('pointerup', ()=>{
    if(S.draft){
      const d=S.draft;
      const ok = d.type==='hline' ? true : Math.abs((d.i2-d.i1))>1;
      if(ok){ S.drawings.push(d); S.selected=d; }
      S.draft=null;
      renderDrawList();
    }
    S.drag=null; render();
  });
  c.addEventListener('wheel', e=>{
    e.preventDefault();
    const r=c.getBoundingClientRect(), x=e.clientX-r.left;
    const anchor = IX(x);
    const k = e.deltaY>0 ? 1.15 : 0.87;
    S.view.i0 = anchor + (S.view.i0-anchor)*k;
    S.view.i1 = anchor + (S.view.i1-anchor)*k;
    clampView(); render();
  }, {passive:false});
  c.addEventListener('pointerleave', ()=>{ S.hover=null; render(); });
  c.addEventListener('dblclick', ()=>{ fitView(); render(); });

  window.addEventListener('keydown', e=>{
    if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)) return;
    const map={'1':'cursor','2':'hline','3':'trend','4':'rect','5':'fib','6':'vline'};
    if(map[e.key]) setTool(map[e.key]);
    if((e.key==='Delete'||e.key==='Backspace') && S.selected){
      S.drawings = S.drawings.filter(d=>d!==S.selected); S.selected=null; renderDrawList(); render();
    }
    if(e.key==='Escape'){ S.draft=null; S.selected=null; setTool('cursor'); renderDrawList(); render(); }
  });
}
function clampView(){
  const n = S.bars.length; if(!n) return;
  let span = S.view.i1 - S.view.i0;
  span = clamp(span, 12, n);
  S.view.i1 = S.view.i0 + span;
  if(S.view.i0 < -5){ S.view.i0=-5; S.view.i1=S.view.i0+span; }
  if(S.view.i1 > n+5){ S.view.i1=n+5; S.view.i0=S.view.i1-span; }
}
function fitView(){
  const n=S.bars.length;
  S.view={i0:-1, i1:Math.max(20,n+1)};
  clampView();
}
function hitTest(x,y){
  for(let k=S.drawings.length-1;k>=0;k--){
    const d=S.drawings[k];
    if(d.type==='hline' && Math.abs(Y(d.p1)-y)<6) return d;
    if(d.type==='vline' && Math.abs(X(d.i1)-x)<6) return d;
    if(d.type==='trend'){
      const [x1,y1]=[X(d.i1),Y(d.p1)], [x2,y2]=[X(d.i2),Y(d.p2)];
      if(distSeg(x,y,x1,y1,x2,y2)<7) return d;
    }
    if(d.type==='rect'){
      const x1=X(d.i1),x2=X(d.i2),y1=Y(d.p1),y2=Y(d.p2);
      if(x>=Math.min(x1,x2)-4&&x<=Math.max(x1,x2)+4&&y>=Math.min(y1,y2)-4&&y<=Math.max(y1,y2)+4) return d;
    }
    if(d.type==='fib'){
      const [x1,y1]=[X(d.i1),Y(d.p1)], [x2,y2]=[X(d.i2),Y(d.p2)];
      if(distSeg(x,y,x1,y1,x2,y2)<7) return d;
    }
  }
  return null;
}
function distSeg(px,py,x1,y1,x2,y2){
  const dx=x2-x1, dy=y2-y1, L=dx*dx+dy*dy;
  let t = L? ((px-x1)*dx+(py-y1)*dy)/L : 0;
  t=clamp(t,0,1);
  return Math.hypot(px-(x1+t*dx), py-(y1+t*dy));
}

function setTool(t){
  S.tool=t;
  $$('#tools .tool').forEach(b=>b.classList.toggle('active', b.dataset.tool===t));
  const hints={cursor:'Клик — выбрать объект, перетащить; протяжка — сдвинуть график.',
    hline:'Клик — поставить горизонтальный уровень.', trend:'Протяни от первой точки ко второй.',
    rect:'Протяни прямоугольник — зона или канал.', fib:'Протяни от начала движения к концу — сетка Фибоначчи.',
    vline:'Клик — вертикальная метка.'};
  $('#toolhint').textContent = hints[t]||'';
  cvs().style.cursor = t==='cursor'?'default':'crosshair';
}

function renderDrawList(){
  const ul=$('#drawlist'); ul.innerHTML='';
  $('#dcount').textContent = S.drawings.length;
  S.drawings.forEach(d=>{
    const li=document.createElement('li');
    if(d===S.selected) li.className='sel';
    const sw=document.createElement('span'); sw.className='sw'; sw.style.background=objColor(d);
    const nm=document.createElement('span'); nm.className='nm';
    let extra='';
    if(d.type==='hline') extra=` ${d.p1.toFixed(2)}`;
    if(d.type==='rect') extra=` ${Math.min(d.p1,d.p2).toFixed(0)}–${Math.max(d.p1,d.p2).toFixed(0)}`;
    if(d.type==='fib') extra=` ${d.p1.toFixed(0)}→${d.p2.toFixed(0)}`;
    nm.textContent = OBJ_LABEL[d.type]+extra;
    const test=document.createElement('button'); test.className='mini'; test.textContent='проверить';
    test.onclick=(e)=>{ e.stopPropagation(); testDrawing(d); };
    const del=document.createElement('button'); del.className='mini'; del.textContent='✕';
    del.onclick=(e)=>{ e.stopPropagation(); S.drawings=S.drawings.filter(x=>x!==d);
      if(S.selected===d) S.selected=null; renderDrawList(); render(); };
    li.append(sw,nm,test,del);
    li.onclick=()=>{ S.selected=d; renderDrawList(); render(); };
    ul.appendChild(li);
  });
}

/* ---------- проверка нарисованного ---------- */
async function testDrawing(d){
  busy(true,'проверяю нарисованное…');
  try{
    const common = {symbol:S.symbol, interval:S.interval, limit:S.limit,
      fee:$('#fee').value/100, slippage:$('#slip').value/100, capital:1};
    let variants=[];
    if(d.type==='hline'){
      variants=[
        {label:'уровень: пробой вверх (лонг выше)', key:'level_breakout',
         extra:{price:d.p1.toFixed(4), direction:'up'}},
        {label:'уровень: покупка от него (отскок)', key:'level_breakout',
         extra:{price:d.p1.toFixed(4), direction:'down'}}];
    } else if(d.type==='trend'){
      const base={i1:Math.round(d.i1), p1:d.p1.toFixed(4), i2:Math.round(d.i2), p2:d.p2.toFixed(4)};
      variants=[
        {label:'трендлайн: пробой вверх', key:'trendline', extra:{...base, side:'up'}},
        {label:'трендлайн: пробой вниз', key:'trendline', extra:{...base, side:'down'}}];
    } else if(d.type==='rect'){
      variants=[{label:'канал: покупка у низа, продажа у верха', key:'range_trade',
        extra:{low:Math.min(d.p1,d.p2).toFixed(4), high:Math.max(d.p1,d.p2).toFixed(4)}}];
    } else if(d.type==='fib'){
      variants=[{label:'Фибоначчи: откат к 61,8%', key:'fib', extra:{lookback:120, entry:0.618}}];
    } else {
      alert('Вертикальная метка — просто отметка, стратегии не задаёт. Используй уровень, трендлайн, зону или Фибоначчи.');
      busy(false); return;
    }
    const rows=[]; let first=null;
    for(const v of variants){
      const res = await api('api/backtest', {...common, ...v.extra, strategy:v.key});
      if(!first) first=res;
      rows.push({...res.summary, strategy:v.label});
    }
    S.result = first;
    renderMetrics(first.summary);
    renderEquity(first.equity, first.benchmark_curve);
    renderVerdict(first.summary, first);
    S.lastRows = rows; S.tab='table'; setTab('table'); renderOut();
    render();
    setStatus(`проверено вариантов: ${rows.length}`);
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

/* ---------- результаты ---------- */
function showResult(res){
  S.result = res;
  const s = res.summary;
  renderMetrics(s);
  renderEquity(res.equity, res.benchmark_curve);
  renderVerdict(s, res);
  S.lastRows = [s];
  renderOut();
  render();
}
function renderMetrics(s){
  const box=$('#metrics'); box.innerHTML='';
  const rows=[
    ['Итог стратегии', pct(s.total_return), cls(s.total_return)],
    ['Купил и держу', pct(s.benchmark_return), cls(s.benchmark_return)],
    ['Разница', pct(s.excess), cls(s.excess)],
    ['В год (CAGR)', pct(s.cagr), cls(s.cagr)],
    ['Волатильность', pct(s.vol), ''],
    ['Sharpe', fmt(s.sharpe,2), cls(s.sharpe)],
    ['Макс. просадка', pct(s.max_drawdown), 'neg'],
    ['Сделок', s.trades, ''],
    ['Успешных', s.trades?pct(s.win_rate):'—', ''],
    ['Комиссии', pct(s.fees_paid), 'neg'],
    ['В рынке', pct(s.exposure), ''],
    ['Баров', s.bars, ''],
  ];
  for(const [k,v,c] of rows){
    const d=document.createElement('div'); d.className='kv';
    d.innerHTML=`<span>${k}</span><b class="${c}">${v}</b>`;
    box.appendChild(d);
  }
}
function renderEquity(eq, bench){
  const c=$('#equity'); const g=fitCanvas(c);
  const W=c.clientWidth,H=c.clientHeight;
  g.clearRect(0,0,W,H);
  if(!eq||!eq.length) return;
  const all=[...eq,...(bench||[])], lo=Math.min(...all), hi=Math.max(...all);
  const X2=i=>4+(i/(eq.length-1))*(W-8);
  const Y2=v=>H-6-((v-lo)/Math.max(1e-9,hi-lo))*(H-14);
  g.strokeStyle='#39424f'; g.setLineDash([3,3]);
  g.beginPath(); (bench||[]).forEach((v,i)=> i?g.lineTo(X2(i),Y2(v)):g.moveTo(X2(i),Y2(v))); g.stroke();
  g.setLineDash([]);
  const good = eq[eq.length-1]>=eq[0];
  g.strokeStyle = good?COL.up:COL.dn; g.lineWidth=1.6;
  g.beginPath(); eq.forEach((v,i)=> i?g.lineTo(X2(i),Y2(v)):g.moveTo(X2(i),Y2(v))); g.stroke();
  g.lineWidth=1;
  $('#eqnote').textContent = `итог ${pct(eq[eq.length-1]/eq[0]-1)} · держать ${bench&&bench.length?pct(bench[bench.length-1]/bench[0]-1):'—'}`;
}

function renderVerdict(s, res){
  const v=$('#verdict'); const L=[];
  const hold = s.benchmark_return;
  if(s.excess > 0.001) L.push(`<span class="good">Обгоняет «купил и держу» на ${pct(s.excess)}.</span>`);
  else if(s.excess < -0.001) L.push(`<span class="bad">Проигрывает «купил и держу» на ${pct(Math.abs(s.excess))} — стратегия хуже простого удержания.</span>`);
  else L.push(`<span class="mid">Практически совпадает с удержанием.</span>`);

  if(s.trades > 0 && s.fees_paid > 0.02)
    L.push(`Комиссии съели <b>${pct(s.fees_paid)}</b> капитала за ${s.trades} сделок.`);
  if(s.trades > 60)
    L.push(`<span class="mid">${s.trades} сделок — частая торговля почти всегда проигрывает комиссиям.</span>`);
  if(s.max_drawdown < -0.4)
    L.push(`<span class="bad">Просадка ${pct(s.max_drawdown)} — такой риск тяжело пересидеть.</span>`);
  if(s.trades === 0)
    L.push(`<span class="bad">Правило ни разу не сработало на этом периоде — проверять нечего. Попробуй другой уровень или таймфрейм.</span>`);
  else if(s.trades < 3)
    L.push(`<span class="mid">Меньше 3 сделок — статистики нет, результат случаен.</span>`);
  if(res && res.trades && res.trades.some(t=>t.reason==='stop_loss'))
    L.push(`Стоп-лосс срабатывал — он меняет форму результата, но не создаёт доход.`);

  if(res && res.robust) {
    L.push(res.robust.p_value > 0.05
      ? `<span class="bad">Тест на случайность: p=${fmt(res.robust.p_value,3)} — неотличимо от случайного входа.</span>`
      : `<span class="mid">Тест на случайность: p=${fmt(res.robust.p_value,3)} — лучше случайного, но проверь на другой монете.</span>`);
  }
  if(!L.length) L.push('Сравни с «купил и держу» — это планка, которую надо обогнать.');
  v.innerHTML = L.join('<br>');
}

function renderOut(){
  const out=$('#out');
  if(S.tab==='json'){
    out.innerHTML = `<pre>${JSON.stringify(S.lastRows, null, 2).replace(/</g,'&lt;')}</pre>`; return;
  }
  if(S.tab==='trades'){
    const r=S.result;
    if(!r||!r.trades||!r.trades.length){ out.innerHTML='<p class="note">Сделок нет.</p>'; return; }
    let h='<table><thead><tr><th>#</th><th>Сторона</th><th>Вход</th><th>Выход</th><th>Цена вх.</th><th>Цена вых.</th><th>Итог</th><th>Причина</th><th>Баров</th></tr></thead><tbody>';
    r.trades.forEach((t,i)=>{
      h+=`<tr><td>${i+1}</td><td>${t.side==='long'?'лонг':'шорт'}</td><td>${dt(t.entry_t)}</td>`+
         `<td>${t.exit_t?dt(t.exit_t):'—'}</td><td>${fmt(t.entry_px,2)}</td><td>${t.exit_px?fmt(t.exit_px,2):'—'}</td>`+
         `<td class="${cls(t.pnl)}">${t.exit_px?pct(t.pnl):'—'}</td><td>${t.reason||'—'}</td><td>${t.bars_held}</td></tr>`;
    });
    out.innerHTML = h+'</tbody></table>';
    return;
  }
  const rows = S.lastRows;
  if(!rows || !rows.length){ out.innerHTML='<p class="note">Пока пусто. Запусти проверку справа.</p>'; return; }
  const keys = ['strategy','total_return','benchmark_return','excess','cagr','vol','sharpe','max_drawdown','trades','win_rate','fees_paid'];
  const head = ['Стратегия','Итог','Держать','Разница','В год','Волат.','Sharpe','Просадка','Сделок','Успешных','Комиссии'];
  let h='<table><thead><tr>'+head.map(x=>`<th>${x}</th>`).join('')+'</tr></thead><tbody>';
  for(const r of rows){
    if(r.error){ h+=`<tr><td>${r.strategy}</td><td colspan="10" class="neg">${r.error}</td></tr>`; continue; }
    h+='<tr>';
    h+=`<td>${r.strategy}</td>`;
    h+=`<td class="${cls(r.total_return)}">${pct(r.total_return)}</td>`;
    h+=`<td class="${cls(r.benchmark_return)}">${pct(r.benchmark_return)}</td>`;
    h+=`<td class="${cls(r.excess)}">${pct(r.excess)}</td>`;
    h+=`<td>${pct(r.cagr)}</td><td>${pct(r.vol)}</td><td>${fmt(r.sharpe,2)}</td>`;
    h+=`<td class="neg">${pct(r.max_drawdown)}</td><td>${r.trades}</td>`;
    h+=`<td>${r.trades?pct(r.win_rate):'—'}</td><td class="neg">${pct(r.fees_paid)}</td>`;
    h+='</tr>';
  }
  out.innerHTML = h+'</tbody></table>'+
    '<p class="note">«Держать» — доходность простого удержания монеты за тот же период. Обогнать её — минимум для любой стратегии.</p>';
}

/* ---------- панель стратегий ---------- */
async function loadStrategies(){
  const j = await api('api/strategies');
  S.strategies = j.strategies;
  const sel=$('#strategy'); sel.innerHTML='';
  const groups={};
  for(const s of S.strategies){ (groups[s.group]=groups[s.group]||[]).push(s); }
  for(const [g,items] of Object.entries(groups)){
    const og=document.createElement('optgroup'); og.label=g;
    for(const it of items){
      const o=document.createElement('option'); o.value=it.key; o.textContent=it.label; og.appendChild(o);
    }
    sel.appendChild(og);
  }
  sel.value='ma_cross';
  sel.onchange=renderParams;
  renderParams();
}
function renderParams(){
  const key=$('#strategy').value;
  const st = S.strategies.find(s=>s.key===key);
  const box=$('#params'); box.innerHTML='';
  if(!st) return;
  if(!st.params.length){ box.innerHTML='<p class="hint">Параметров нет.</p>'; return; }
  for(const p of st.params){
    const lab=document.createElement('label'); lab.className='fld';
    lab.innerHTML=`<span>${p.label}</span>`;
    const inp=document.createElement('input'); inp.type='number'; inp.step='any';
    inp.value=p.default; inp.dataset.param=p.name;
    lab.appendChild(inp); box.appendChild(lab);
  }
  if(st.group==='Рисование')
    box.insertAdjacentHTML('beforeend','<p class="hint">Эти стратегии обычно задаются нарисованным объектом — жми «проверить» у объекта слева.</p>');
}
function collectParams(){
  const o={};
  $$('#params input').forEach(i=>{ o[i.dataset.param]=i.value; });
  return o;
}
function riskParams(){
  const o={};
  if($('#stop').value) o.stop=$('#stop').value/100;
  if($('#tp').value) o.tp=$('#tp').value/100;
  if($('#trail').value) o.trail=$('#trail').value/100;
  return o;
}

/* ---------- кнопки ---------- */
async function loadBars(){
  busy(true,'загружаю данные…');
  try{
    const j = await api('api/bars', {symbol:S.symbol, interval:S.interval, limit:S.limit});
    S.bars = j.bars; S.result=null;
    fitView();
    render(); renderOut(); renderMetricsEmpty();
    setStatus(`${S.bars.length} баров · ${S.symbol}`);
  }catch(e){ alert('Не загрузилось: '+e.message); setStatus('ошибка'); }
  busy(false);
}
function renderMetricsEmpty(){
  $('#metrics').innerHTML='<p class="note" style="grid-column:1/-1">Здесь появятся метрики проверки.</p>';
  $('#verdict').textContent='Нажми «Проверить гипотезу».';
}

async function runBacktest(){
  busy(true,'прогоняю стратегию…');
  try{
    const res = await api('api/backtest',
      {symbol:S.symbol, interval:S.interval, limit:S.limit,
       fee:$('#fee').value/100, slippage:$('#slip').value/100, capital:1,
       strategy:$('#strategy').value, ...collectParams(), ...riskParams()});
    showResult(res);
    setStatus('проверка готова');
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

async function runScan(){
  busy(true,'прогоняю все стратегии…');
  try{
    const j = await api('api/scan', {symbol:S.symbol, interval:S.interval, limit:S.limit,
      fee:$('#fee').value/100, slippage:$('#slip').value/100});
    S.lastRows = j.results; S.tab='table'; setTab('table');
    renderOut(); setStatus(`${j.results.length} стратегий`);
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

async function runStops(){
  busy(true,'проверяю стоп-лоссы…');
  try{
    const j = await api('api/stops', {symbol:S.symbol, interval:S.interval, limit:S.limit,
      fee:$('#fee').value/100});
    S.lastRows = j.results.map(r=>({strategy:r.rule, total_return:r.return, benchmark_return:j.benchmark,
      excess:r.vs_hold, trades:r.trades, max_drawdown:r.max_drawdown}));
    S.tab='table'; setTab('table'); renderOut();
    $('#verdict').innerHTML = `Стоп-лосс не создаёт доход — он только меняет форму результата. `+
      `Без стопа: <b>${pct(j.benchmark)}</b>. Любой стоп на этом периоде хуже.`;
    setStatus('стопы проверены');
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

async function runRobust(){
  busy(true,'тест на случайность (200 прогонов)…');
  try{
    const j = await api('api/robust', {symbol:S.symbol, interval:S.interval, limit:S.limit,
      fee:$('#fee').value/100, strategy:$('#strategy').value, trials:200, ...collectParams()});
    const r=S.result; if(r){ r.robust=j; renderVerdict(r.summary, r); }
    S.lastRows = [{strategy:$('#strategy').value+' (тест)', total_return:j.real_return,
      benchmark_return:j.benchmark, excess:j.real_return-j.benchmark, trades:'—',
      max_drawdown:'—', random_mean:j.random_mean, p95:j.p95, p_value:j.p_value}];
    S.tab='json'; setTab('json'); renderOut();
    setStatus('тест готов');
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

async function runFunding(){
  busy(true,'считаю фандинг…');
  try{
    const j = await api('api/funding', {symbol:S.symbol, limit:500});
    S.lastRows=[{strategy:'фандинг-карри', annual:j.annual, positive_share:j.positive_share, n:j.n}];
    S.tab='json'; setTab('json'); renderOut();
    $('#verdict').innerHTML = `Фандинг-карри (лонг спот + шорт перп): <b>${pct(j.annual)}</b> в год до комиссий. `+
      `Положительных выплат ${pct(j.positive_share)}. Это доход на капитал — без капитала он не работает.`;
    setStatus('фандинг посчитан');
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

/* ---------- оверлеи ---------- */
async function findLevels(){
  busy(true,'ищу уровни (это займёт пару секунд)…');
  try{
    const j = await api('api/levels', {symbol:S.symbol, interval:S.interval, limit:S.limit,
      k:5, tol:0.02, trials:60, top:12});
    S.overlays.levels = j.levels;
    S.lastRows = j.levels.map(l=>({strategy:`уровень ${l.price.toFixed(0)}`, touches:l.touches,
      hold_rate:l.hold_rate, broke_up:l.broke_up, broke_down:l.broke_down, p_value:l.p_value}));
    S.tab='json'; setTab('json'); renderOut(); render();
    const sig = j.levels.filter(l=>l.p_value<=0.05).length;
    $('#verdict').innerHTML = `Найдено уровней: <b>${j.levels.length}</b>. `+
      `Отличий от случайного блуждания (p≤0,05): <b>${sig}</b>. `+
      (sig===0 ? 'То есть цена у этих уровней ведёт себя как у случайно нарисованных — «рисование» само по себе преимущества не даёт.'
               : 'Есть уровни со статистикой лучше случайной — проверь их пробой отдельно.');
    setStatus(`уровней: ${j.levels.length}`);
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}
async function findTrend(){
  busy(true,'строю трендлайны…');
  try{
    const j = await api('api/trendlines', {symbol:S.symbol, interval:S.interval, limit:S.limit, k:5});
    S.overlays.trendlines = j.trendlines;
    S.lastRows = j.trendlines;
    S.tab='json'; setTab('json'); renderOut(); render();
    setStatus(`трендлайнов: ${j.trendlines.length}`);
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}
async function findPatterns(){
  busy(true,'ищу фигуры…');
  try{
    const j = await api('api/patterns', {symbol:S.symbol, interval:S.interval, limit:S.limit, horizon:20});
    S.overlays.patterns = j.patterns;
    S.lastRows = j.patterns;
    S.tab='json'; setTab('json'); renderOut(); render();
    const withEdge = j.patterns.filter(p=>p.edge_vs_base!==undefined);
    const avg = withEdge.length ? withEdge.reduce((a,p)=>a+p.edge_vs_base,0)/withEdge.length : 0;
    $('#verdict').innerHTML = `Фигур найдено: <b>${j.patterns.length}</b>. `+
      `Среднее превышение над обычным ходом цены: <b class="${cls(avg)}">${pct(avg)}</b>. `+
      (Math.abs(avg)<0.01 ? 'Фигуры на этом периоде не дают статистического преимущества.' : 'Отклонение есть — но проверь на другой монете и периоде.');
    setStatus(`фигур: ${j.patterns.length}`);
  }catch(e){ alert('Ошибка: '+e.message); }
  busy(false);
}

function setTab(t){
  S.tab=t;
  $$('.tab').forEach(b=>b.classList.toggle('active', b.dataset.tab===t));
  renderOut();
}

/* ---------- код доступа ---------- */
function showGate(){ $('#gate').classList.remove('hidden'); $('#gatecode').focus(); }
function hideGate(){ $('#gate').classList.add('hidden'); }
async function tryGate(){
  const code = $('#gatecode').value.trim();
  if(!code) return;
  const btn = $('#gatebtn'); btn.disabled = true;
  $('#gateerr').textContent = 'Проверяю…';
  try{
    const u = new URL('api/health', location.href);
    u.searchParams.set('token', code);
    const r = await fetch(u);
    if(r.ok){
      MEM_TOKEN = code;
      let stored = false;
      try{ localStorage.setItem('lab_token', code); stored = localStorage.getItem('lab_token') === code; }catch(e){}
      hideGate();
      $('#gateerr').textContent = '';
      setStatus(stored ? 'доступ открыт' : 'доступ открыт — браузер не сохраняет вход, не закрывай вкладку');
      await boot();          /* догружаем интерфейс без перезагрузки страницы */
      return;
    }
    $('#gateerr').textContent = (r.status === 401)
      ? 'Код не подошёл. Скопируй заново — возможно, попал лишний символ или пробел.'
      : 'Сервер ответил ' + r.status + '. Попробуй ещё раз через минуту.';
  }catch(e){
    $('#gateerr').textContent = 'Нет связи с сервером: ' + e.message;
  }
  btn.disabled = false;
}
document.addEventListener('DOMContentLoaded', ()=>{
  $('#gatebtn').addEventListener('click', tryGate);
  $('#gatecode').addEventListener('keydown', e=>{ if(e.key==='Enter') tryGate(); });
});

/* ---------- старт ---------- */
async function boot(){
  try{
    const t0 = new URL(location.href).searchParams.get('token');
    if(t0){ MEM_TOKEN = t0.trim(); try{ localStorage.setItem('lab_token', MEM_TOKEN); }catch(e){} }
  }catch(e){}
  try{
    const j = await api('api/symbols');
    const dl=$('#symbols'); dl.innerHTML='';
    for(const s of j.symbols){ const o=document.createElement('option'); o.value=s; dl.appendChild(o); }
  }catch(e){}

  let saved = {};
  try{ saved = JSON.parse(localStorage.getItem('lab')||'{}') || {}; }catch(e){}
  if(saved.symbol) $('#symbol').value=saved.symbol;
  if(saved.interval) $('#interval').value=saved.interval;
  if(saved.limit) $('#limit').value=saved.limit;
  if(saved.fee!==undefined) $('#fee').value=saved.fee;
  if(saved.capital!==undefined) $('#capital').value=saved.capital;
  if(saved.drawings) { S.drawings = saved.drawings; S.nextId = saved.nextId||1; }

  S.symbol=$('#symbol').value; S.interval=$('#interval').value; S.limit=+$('#limit').value;

  await loadStrategies();
  bindChart();
  setTool('cursor');

  $('#load').onclick = ()=>{ save(); S.symbol=$('#symbol').value.toUpperCase();
    S.interval=$('#interval').value; S.limit=+$('#limit').value; loadBars(); };
  $('#symbol').addEventListener('keydown', e=>{ if(e.key==='Enter') $('#load').click(); });
  $('#runBt').onclick = runBacktest;
  $('#runScan').onclick = runScan;
  $('#runStops').onclick = runStops;
  $('#runRobust').onclick = runRobust;
  $('#runFunding').onclick = runFunding;
  $('#findLevels').onclick = findLevels;
  $('#findTrend').onclick = findTrend;
  $('#findPatterns').onclick = findPatterns;
  $('#clearOverlay').onclick = ()=>{ S.overlays={levels:[],trendlines:[],patterns:[]}; render(); };
  $('#clearDraw').onclick = ()=>{ S.drawings=[]; S.selected=null; renderDrawList(); render(); save(); };
  $$('#tools .tool').forEach(b=> b.onclick=()=>setTool(b.dataset.tool));
  $$('.tab').forEach(b=> b.onclick=()=>setTab(b.dataset.tab));
  window.addEventListener('resize', ()=>render());

  renderDrawList();
  await loadBars();
}
function save(){
  try{
    localStorage.setItem('lab', JSON.stringify({
      symbol:$('#symbol').value, interval:$('#interval').value, limit:$('#limit').value,
      fee:$('#fee').value, capital:$('#capital').value,
      drawings:S.drawings, nextId:S.nextId }));
  }catch(e){}
}
window.addEventListener('beforeunload', save);

boot();

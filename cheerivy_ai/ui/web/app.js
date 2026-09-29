// CHEERIVY screen. The laptop (ui/server.py + ui/flow.py) owns the game; this page draws the state
// it streams (GET /events) and forwards keys (POST /key). Field list: ui/README.md.
const $ = id => document.getElementById(id);
const stage = $('stage');
let S = null, scale = 1;
const MATCH = ['prematch', 'ready', 'countdown', 'live', 'goal', 'pause', 'debug'];

// ------------------------------------------------------------------ plumbing
function fit() {
  scale = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${-960 * scale}px, ${-540 * scale}px) scale(${scale})`;
}
addEventListener('resize', fit); fit();

function connect() {
  const es = new EventSource('/events');
  es.onmessage = e => { S = JSON.parse(e.data); S._t = performance.now(); $('offline').classList.add('hidden'); render(); };
  es.onerror = () => { $('offline').classList.remove('hidden'); };
}
connect();
document.querySelector('#caption .skip').onclick = () => sendKey('Tab');

const NO_DEFAULT = ['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Backspace', 'Enter', 'F1', 'Tab'];
addEventListener('keydown', e => {
  if (NO_DEFAULT.includes(e.code)) e.preventDefault();
  if (e.repeat) return;
  if (S && S.screen === 'calibrate') {           // the mouse does the work; a few keys help
    if (S.calib === 'board') {
      if (e.code === 'Enter' || e.code === 'NumpadEnter') calSave();
      else if (e.code === 'KeyU' || e.code === 'Backspace') calUndo();
      else if (e.code === 'Escape') calCancel();
    } else if (e.code === 'Escape' || e.code === 'Enter') sendKey('Escape');
    return;
  }
  if (e.code === 'Backquote') { $('dev').classList.toggle('hidden'); return; }
  if (e.code === 'KeyF' && !e.metaKey && !e.ctrlKey) { document.documentElement.requestFullscreen?.(); return; }
  fetch('/key', { method: 'POST', body: JSON.stringify({ key: e.code }) }).catch(() => {});
});

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function mount(el, key, html) {                 // rebuild only when the structure changes
  if (el.dataset.key === key) return false;
  el.dataset.key = key; el.innerHTML = html; return true;
}
function setText(el, v) { if (el && el.textContent !== String(v)) el.textContent = v; }
function cursor(root) {
  const c = S.menu ? S.menu.cursor : -1;
  root.querySelectorAll('[data-i]').forEach(e => e.classList.toggle('on', +e.dataset.i === c));
}
const mmss = s => { s = Math.max(0, Math.ceil(s - 1e-6)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const side = p => (p === 1 ? 'p1' : 'p2');
const isAI = () => S.mode === 'ai' || S.mode === 'aivai';   // side 2 is the machine
const MODE_LABEL = { ai: 'VS MACHINE', '2p': '2 PLAYERS', aivai: 'AI VS AI' };

// ------------------------------------------------------------------ calibration clicks
const CAL_STEPS = ['A corner of the wall behind <b class="t2">PLAYER 2 / THE AI</b>', 'The <b>other</b> corner of that same wall',
  'A corner of the wall behind <b class="t1">PLAYER 1</b>', 'The <b>other</b> corner of that same wall'];
let calPts = [], calPing = null, calTimer = 0;
const sendKey = key => fetch('/key', { method: 'POST', body: JSON.stringify({ key }) }).catch(() => {});
const calUndo = () => { calPts.pop(); calDraw(); };
const calSave = () => { if (calPts.length === 4) fetch('/calib', { method: 'POST', body: JSON.stringify({ points: calPts }) }).catch(() => {}); };
const calCancel = () => sendKey('Escape');       // the game decides (no cancelling the very first calibration)
function calDraw() {
  const el = document.querySelector('.cal'); if (!el) return;
  const img = el.querySelector('img'), svg = el.querySelector('svg'), w = img.naturalWidth, h = img.naturalHeight;
  el.classList.toggle('ready', w > 0);
  const step = el.querySelector('.cal-step');
  if (step) setText(step, calPts.length < 4 ? `STEP ${calPts.length + 1} OF 4` : 'ALL 4 CLICKED · PRESS SAVE');
  el.querySelectorAll('.cal-list li').forEach((li, i) => { li.classList.toggle('done', i < calPts.length); li.classList.toggle('now', i === calPts.length && S.calib === 'board'); });
  const save = el.querySelector('[data-do=save]'); if (save) save.disabled = calPts.length !== 4;
  if (!w) return;
  const fitW = Math.round(w * Math.min(1120 / w, 860 / h)) + 'px';   // as big as the space allows
  if (img.style.width !== fitW) img.style.width = fitW;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const r = w / 90, col = i => (i < 2 ? 'var(--p2)' : 'var(--p1)');
  let out = '';
  if (calPts.length > 1) out += `<${calPts.length < 4 ? 'polyline fill="none"' : 'polygon fill="rgba(255,255,255,.08)"'} points="${calPts.map(p => p.join(',')).join(' ')}" stroke="#fff" stroke-width="${r / 3}"/>`;
  calPts.forEach((p, i) => { out += `<circle cx="${p[0]}" cy="${p[1]}" r="${r}" fill="${col(i)}" stroke="#000" stroke-width="${r / 4}"/>
    <text x="${p[0] + r * 1.4}" y="${p[1] - r * 1.2}" font-size="${r * 2.4}" font-weight="800" fill="#fff" stroke="#000" stroke-width="${r / 5}" paint-order="stroke">${i + 1}</text>`; });
  if (calPing && performance.now() - calPing[3] < 1500) {
    const [x, y, what] = calPing;
    out += `<circle cx="${x}" cy="${y}" r="${r * 1.6}" fill="none" stroke="${what === 'ball' ? 'var(--gold)' : '#fff'}" stroke-width="${r / 3}"/>`;
  }
  if (svg.innerHTML !== out) svg.innerHTML = out;
}

const hints = (...h) => `<div class="hints">${h.map(([g, t]) => `<div class="hint">${
  g === 'btn' ? '<i class="btn"></i>' : `<i class="stick ${g === 'v' ? 'v' : ''}"></i>`}${t}</div>`).join('')}</div>`;
const steps = (n, of) => `<span class="steps">${Array.from({ length: of }, (_, i) => `<i class="${i < n ? 'done' : ''}"></i>`).join('')}</span>`;

// ------------------------------------------------------------------ full screens
const SCREENS = {
  home: () => ['home', `
    <div class="screen home">
      <div class="brand">
        <div class="kicker">CSE316 · Robot ball duel</div>
        <div class="logo">CHEERIVY</div>
        <div class="tag">For three minutes, a lab table becomes a stadium.</div>
      </div>
      <div class="tiles">
        <div class="tile opt" data-i="0"><div class="art"><div class="half p1">P1</div><div class="half p2 ai">AI</div></div>
          <div class="vs">VS</div><div class="label"><b>VS MACHINE</b><span>You against CHEERIVY AI</span></div></div>
        <div class="tile opt" data-i="1"><div class="art"><div class="half p1">P1</div><div class="half p2">P2</div></div>
          <div class="vs">VS</div><div class="label"><b>2 PLAYERS</b><span>Head to head</span></div></div>
        <div class="tile opt" data-i="2"><div class="art"><div class="half p1 ai">AI</div><div class="half p2 ai">AI</div></div>
          <div class="vs">VS</div><div class="label"><b>AI VS AI</b><span>Watch the machines play</span></div></div>
        <div class="tile small opt" data-i="3"><div class="gear"></div><div class="label"><b>SETTINGS</b><span>Sound · servos · camera</span></div></div>
      </div>
      ${hints(['h', 'Choose'], ['btn', 'Confirm'])}
    </div>`],

  attract: () => ['attract', `
    <div class="screen attract">
      <div class="logo">CHEERIVY</div>
      <div class="press">PRESS <i class="btn"></i> TO PLAY</div>
      <div class="modes">VS MACHINE · 2 PLAYERS</div>
    </div>`],

  difficulty: () => {
    const D = [['EASY', 1, 'Slow to react. Perfect for a first match.'],
      ['MEDIUM', 2, 'Reads your shots and moves early.'],
      ['HARD', 3, 'Predicts every bounce. Good luck.']];
    return ['difficulty' + S.mode, `
    <div class="screen setup">
      <div class="head"><div class="kicker">${MODE_LABEL[S.mode] || ''} ${steps(1, 2)}</div><div class="question">${S.mode === 'aivai' ? 'How smart are the machines?' : 'How smart is the machine?'}</div></div>
      <div class="cards">${D.map(([n, lv, d], i) => `
        <div class="card cool opt" data-i="${i}"><div class="meter">${[1, 2, 3].map(k => `<i class="${k <= lv ? 'lit' : ''}"></i>`).join('')}</div>
          <b>${n}</b><span>${d}</span></div>`).join('')}</div>
      <div class="back-pill" data-i="3">BACK</div>
      ${hints(['h', 'Choose'], ['btn', 'Confirm'])}
    </div>`];
  },

  join: () => ['join', `
    <div class="screen setup">
      <div class="head"><div class="kicker">2 PLAYERS ${steps(1, 2)}</div><div class="question">Who's playing?</div></div>
      <div class="join-cards">
        <div class="slot p1"><div class="tag">P1</div><b>PLAYER ONE</b><span>READY ✓</span></div>
        <div class="slot p2"><div class="tag">P2</div><b>PLAYER TWO</b><span>PRESS <i class="btn sm"></i> TO JOIN</span></div>
      </div>
      <div class="vs-mid">VS</div>
      ${hints(['btn', 'Player two joins'], ['v', 'Hold down: back'])}
    </div>`],

  length: () => {
    const L = [[60, '1', 'Quick fire'], [120, '2', 'Short match'], [180, '3', 'Full match'], [300, '5', 'Marathon']];
    return ['length', `
    <div class="screen setup">
      <div class="head"><div class="kicker">${MODE_LABEL[S.mode] || ''} ${steps(2, 2)}</div><div class="question">How long is the match?</div></div>
      <div class="cards">${L.map(([, n, d], i) => `
        <div class="card neutral opt" data-i="${i}" style="width:360px"><div class="big">${n}<small>MIN</small></div><span>${d}</span></div>`).join('')}</div>
      <div class="note">Level at the end? The <b>golden goal</b> decides it.</div>
      <div class="back-pill" data-i="4">BACK</div>
      ${hints(['h', 'Choose'], ['btn', 'Start'])}
    </div>`];
  },

  settings: () => {
    const m = S.menu, group = m.group;
    const DESC = { SOUND: 'Commentary and crowd volume', GAMEPLAY: 'Match length, golden goal, freeze',
      'SERVO TUNING': 'Rest angle and swing of both strikers', 'CAMERA & AI': 'Calibration, colours, debug view' };
    const rows = m.items.map((it, i) => {
      if (it.id === 'back') return `<div class="row back" data-i="${i}">BACK</div>`;
      if (!group) return `<div class="row" data-i="${i}"><b>${esc(it.label)}</b><span class="desc">${DESC[it.label] || ''}</span></div>`;
      const right = it.value === undefined
        ? `<span class="act">PRESS <i class="btn sm"></i></span>`
        : `<span class="val ${/^(ON|OFF)$/.test(it.value) ? 'on-off' : ''}"><span class="arr">◀</span><span data-v="${i}"></span><span class="arr">▶</span></span>`;
      return `<div class="row" data-i="${i}">${esc(it.label)}${right}</div>`;
    }).join('');
    return ['settings:' + (group || ''), `
    <div class="screen settings">
      <div class="head"><div class="kicker">SETTINGS${group ? ' · ' + esc(group).toUpperCase() : ''}</div>
        <div class="question">${group ? esc(group) : 'Settings'}</div></div>
      <div class="rows ${group ? '' : 'groups'}">${rows}</div>
      ${hints(['v', 'Choose'], ...(group ? [['h', 'Change']] : []), ['btn', 'Select'])}
    </div>`, root => {
      root.querySelectorAll('[data-v]').forEach(e => {
        const v = m.items[+e.dataset.v].value;
        const html = v === 'ON' ? '<span class="yes">ON</span>' : v === 'OFF' ? '<span class="no">OFF</span>' : esc(v);
        if (e.innerHTML !== html) e.innerHTML = html;
      });
    }];
  },

  // Settings > Camera & AI (and start-up without a saved calibration), with the laptop's mouse:
  // "board" = click the board's 4 corners on the camera picture; "colours" = click tape / ball.
  calibrate: () => {
    const board = S.calib === 'board';
    const html = board ? `
    <div class="screen cal">
      <div class="head"><div class="kicker">CAMERA · CALIBRATE</div><div class="question">Click the 4 corners</div></div>
      <div class="cal-side"><div class="cal-step"></div>
        <ol class="cal-list">${CAL_STEPS.map(s => `<li>${s}</li>`).join('')}</ol>
        <div class="cal-note">Click the <b>inside</b> corners, where the board meets the end walls. The game still shows the rails and carriages around it.</div>
        <div class="cal-btns"><button data-do="undo">UNDO <kbd>U</kbd></button>
          <button data-do="save" class="go">SAVE <kbd>ENTER</kbd></button>
          <button data-do="cancel">CANCEL <kbd>ESC</kbd></button></div></div>
      <div class="cal-pic"><div class="cal-frame"><img src="/raw" alt=""><svg class="cal-marks"></svg></div><div class="cal-wait">Waiting for the camera…</div></div>
    </div>` : `
    <div class="screen cal">
      <div class="head"><div class="kicker">CAMERA · COLOURS</div><div class="question">Teach the colours</div></div>
      <div class="cal-side">
        <ol class="cal-list plain"><li><b>LEFT-click</b> the tape on a carriage. The top half teaches the AI side's carriage, the bottom half player 1's.</li>
          <li><b>RIGHT-click</b> the ball.</li></ol>
        <div class="cal-note">The result shows at the bottom of the screen. Click again to correct it.</div>
        <div class="cal-btns"><button data-do="done" class="go">DONE <kbd>ESC</kbd></button></div></div>
      <div class="cal-pic"><div class="cal-frame"><img src="/video" alt=""><svg class="cal-marks"></svg></div><div class="cal-wait">Waiting for the camera…</div></div>
    </div>`;
    return ['calib:' + S.calib, html, root => {
      const el = root.querySelector('.cal');
      if (!el || el.dataset.init) return;
      el.dataset.init = 1;
      calPts = [];
      const img = el.querySelector('img');
      const act = { undo: calUndo, save: calSave, cancel: calCancel, done: () => sendKey('Escape') };
      el.querySelectorAll('[data-do]').forEach(b => b.onclick = () => act[b.dataset.do]());
      img.onmousedown = e => {
        e.preventDefault();
        if (!img.naturalWidth) return;
        const r = img.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width * img.naturalWidth, y = (e.clientY - r.top) / r.height * img.naturalHeight;
        if (board) {
          if (e.button === 0 && calPts.length < 4) calPts.push([Math.round(x), Math.round(y)]);
        } else {
          const what = e.button === 2 ? 'ball' : 'carriage';
          fetch('/sample', { method: 'POST', body: JSON.stringify({ what, x: Math.round(x), y: Math.round(y) }) }).catch(() => {});
          calPing = [x, y, what, performance.now()];
        }
        calDraw();
      };
      img.oncontextmenu = e => e.preventDefault();
      clearInterval(calTimer);
      calTimer = setInterval(() => { if (!document.body.contains(img)) clearInterval(calTimer); else calDraw(); }, 200);
      calDraw();
    }];
  },

  fulltime: () => {
    const r = S.result || { score: S.score, awards: [] }, [a, b] = r.score;
    const win = r.winner ? `${esc(S.names[r.winner])} WINS` : `IT'S A DRAW`;
    return ['fulltime', `
    <div class="screen"><div class="result">
      <div class="kicker">FULL TIME</div>
      <div class="winner" style="${r.winner ? '' : 'color:var(--ink);text-shadow:none'}">${win}</div>
      <div class="final"><span class="nm p1">${esc(S.names[1])}</span><span class="sc">${a} – ${b}</span><span class="nm p2">${esc(S.names[2])}</span></div>
      <div class="awards">${(r.awards || []).map(w => `<div class="award"><b>${esc(w.title)}</b><span class="${side(w.who)}">${esc(S.names[w.who])}</span></div>`).join('')}</div>
    </div></div>`];
  },

  highlights: () => {
    const g = S.goals, L = S.length_s;
    const dots = g.map((x, i) => `<div class="dot ${side(x.scorer)}" data-g="${i}" style="left:${x.golden ? 100 : Math.min(100, x.at / L * 100)}%"></div>`).join('');
    return ['highlights', `
    <div class="screen hl">
      <div class="head"><div class="kicker">FULL TIME · ${esc(S.names[1])} ${S.score[0]} – ${S.score[1]} ${esc(S.names[2])}</div>
        <div class="question">Highlights</div></div>
      <div class="reel"><div class="scan"></div><div class="rec"><i></i>REPLAY</div><div id="hl-card"></div></div>
      <div class="timeline"><div class="track"></div>${dots}</div>
    </div>`, root => {
      const i = S.highlight.index, card = root.querySelector('#hl-card');
      root.querySelectorAll('[data-g]').forEach(e => e.classList.toggle('on', +e.dataset.g === i));
      if (i === null || i === undefined) {
        mount(card, 'end', `<div class="card-hl"><small>${g.length ? 'THAT\'S ALL' : 'NO GOALS TODAY'}</small><b>FROM CHEERIVY</b></div>`);
      } else {
        const x = g[i];
        mount(card, 'g' + i, `<div class="card-hl ${side(x.scorer)}"><small>GOAL ${i + 1} OF ${g.length} · ${x.golden ? 'GOLDEN GOAL' : mmss(x.at)}</small>
          <b>${esc(S.names[x.scorer])}</b><div class="sc">${x.score[0]} – ${x.score[1]}</div></div>`);
      }
    }];
  },
};

// ------------------------------------------------------------------ match (board + scorebug)
let prevScore = [0, 0];
function updateMatch() {
  const ai = isAI();
  setText($('name-1'), S.names[1]); setText($('name-2'), S.names[2]);
  setText($('tag-2'), S.tags[2]); setText($('fz-tag-2'), S.tags[2]);
  setText(document.querySelector('.team.p1 small'), S.tags[1]); setText(document.querySelector('#fz-1 .tagp'), S.tags[1]);
  setText($('tag-top'), S.names[2]); setText($('tag-bottom'), S.names[1]);
  $('team-2').classList.toggle('ai', ai);
  $('board-corner').classList.toggle('sim', !S.board);
  $('board-corner').lastChild.textContent = S.video ? 'AI VISION · LIVE CAMERA' : S.board ? 'AI VISION' : 'AI VISION · SIMULATOR';

  // clock
  const c = $('clock'), t = S.clock, live = S.running;
  setText($('clock-t'), S.golden ? 'GOLDEN GOAL' : mmss(t));
  c.classList.toggle('golden', S.golden);
  c.classList.toggle('warn', !S.golden && t <= 30 && t > 10);
  c.classList.toggle('panic', !S.golden && t <= 10 && live);
  c.classList.toggle('stopped', !live);
  const st = $('clock-state');
  setText(st, live ? '● LIVE' : S.screen === 'pause' ? 'PAUSED' : S.kicked_off ? 'STOPPED' : 'KICK-OFF');
  st.classList.toggle('live', live);

  // score (bump when it changes)
  [1, 2].forEach(p => {
    const n = $('score-' + p);
    setText(n, S.score[p - 1]);
    if (S.score[p - 1] !== prevScore[p - 1]) { n.classList.remove('bump'); void n.offsetWidth; n.classList.add('bump'); }
  });
  prevScore = [...S.score];

  // buzzer panel: race state + who is frozen (bar drains over the freeze)
  const bz = S.buzz, bs = $('buzz-state'), r = bz.result;
  setText(bs, !S.freeze_on ? 'OFF' : bz.open ? 'BUZZ! PRESS' : r ? (r.winner ? `${S.tags[r.winner]} WON IT` : 'NOBODY') : 'WAIT FOR IT');
  bs.classList.toggle('hot', bz.open);
  $('freeze-box').classList.toggle('open', bz.open);
  [1, 2].forEach(p => {
    const f = S.freeze[p], row = $('fz-' + p);
    row.classList.toggle('frozen', f.frozen > 0);
    row.querySelector('i').style.width = (f.frozen > 0 ? 100 * f.frozen / S.freeze_s : 0) + '%';
    setText(row.querySelector('.st'), f.frozen > 0 ? `FROZEN ${Math.ceil(f.frozen)}` : '');
  });

  const rl = $('rally');                          // long rallies: a counter on the board
  rl.classList.toggle('on', S.screen === 'live' && S.rally >= 3);
  setText(rl.querySelector('b'), S.rally);

  mount($('chips'), `${S.mode}${S.difficulty}${S.length_s}`, [
    `<span class="chip">${MODE_LABEL[S.mode] || ''}</span>`,
    ai ? `<span class="chip cool">${esc(S.difficulty)}</span>` : '',
    `<span class="chip">${mmss(S.length_s)} MATCH</span>`].join(''));
}

function overlayFor() {
  const sc = S.screen, n = S.names;
  if (sc === 'prematch') return ['pre', `<div class="dim"></div>
    <div class="versus"><div class="side p1 ${S.mode === 'aivai' ? 'ai' : ''}"><small>${S.mode === 'aivai' ? 'BLUE CARRIAGE' : 'PLAYER 1'}</small><b>${esc(n[1])}</b></div>
      <div class="side p2 ${isAI() ? 'ai' : ''}"><small>${isAI() ? 'THE MACHINE' : 'PLAYER 2'}</small><b>${esc(n[2])}</b></div>
      <div class="vs">VS</div>
      <div class="meta">${mmss(S.length_s)} MATCH${isAI() ? ' · ' + esc(S.difficulty) : ''} · GOLDEN GOAL IF LEVEL</div></div>`];
  if (sc === 'ready') {
    const pl = S.placer, k = S.kicker;
    let who, what, cls;
    if (S.mode === 'aivai') { who = `${n[pl === 2 ? 2 : 1]} · ${S.kicked_off ? 'RESTART' : 'KICK-OFF'}`; what = 'Place the ball in front of its carriage. Either joystick starts.'; cls = side(pl === 2 ? 2 : 1); }
    else if (k === 'any') { who = 'READY TO RESUME'; what = 'Place the ball in front of the player who restarts.'; cls = ''; }
    else if (!S.kicked_off) { who = `${n[1]} · KICK-OFF`; what = 'Place the ball just in front of your carriage.'; cls = 'p1'; }
    else if (isAI() && pl === 2) { who = n[1]; what = 'Place the ball in front of the machine\'s carriage.'; cls = 'p1'; }
    else { who = n[pl]; what = 'Place the ball in front of your carriage.'; cls = side(pl); }
    return ['ready' + k + pl + S.kicked_off, `<div class="ready ${cls}"><div><div class="who">${esc(who)}</div><div class="what">${esc(what)}</div></div>
      <div class="go">PUSH <i class="stick fwd"></i> FORWARD WHEN READY</div></div>`];
  }
  if (sc === 'countdown') {
    if (S.countdown === null) return ['hush', `<div class="count hush"><b>GET READY</b></div>`];
    return ['cd' + S.countdown, `<div class="count"><div class="ring"></div><b>${S.countdown}</b></div>`];
  }
  if (sc === 'live') {
    if (S.countdown === 'GO') return ['go', `<div class="count go"><div class="ring"></div><b>GO!</b></div>`];
    const bz = S.buzz;
    if (bz.open) return ['buzz', `<div class="buzz"><b>BUZZ!</b><span>FIRST TO PRESS <i class="btn sm"></i> FREEZES THE OTHER</span>
      <div class="buzz-bar"><i id="buzz-bar"></i></div></div>`];
    if (bz.result) {
      const w = bz.result.winner;
      if (!w) return ['buzz-none', `<div class="buzz-res"><b>NOBODY TOOK IT</b></div>`];
      return ['buzz-w' + w, `<div class="buzz-res ${side(w)}"><b>${esc(n[w])}</b><span>FREEZES ${esc(n[3 - w])} · ${S.freeze_s}S</span></div>`];
    }
    if (!S.golden && S.running && S.clock <= 5 && S.clock > 0) {
      const k = Math.ceil(S.clock);
      return ['l5' + k, `<div class="last5"><b>${k}</b></div>`];
    }
    return ['none', ''];
  }
  if (sc === 'goal') {
    const [a, b] = S.score, p = S.flash;
    if (!p) return ['golden', `<div class="goal gold"><div class="wipe"></div><div class="streaks"></div>
      <div class="word">GOLDEN GOAL</div><div class="by">The next goal wins it all</div>
      <div class="line"><span>${a} – ${b}</span><small>LEVEL</small></div></div>`];
    const d = a - b, lead = d === 0 ? 'LEVEL' : `${n[d > 0 ? 1 : 2]} LEADS BY ${Math.abs(d)}`;
    return ['goal' + p + a + b, `<div class="goal ${side(p)}"><div class="wipe"></div><div class="streaks"></div>
      <div class="word">GOAL!</div><div class="by">${esc(n[p])}${S.golden ? ' WINS IT' : ''}</div>
      <div class="line"><span>${a} – ${b}</span><small>${S.golden ? 'GOLDEN GOAL' : esc(lead)}</small></div></div>`];
  }
  if (sc === 'debug') {
    const d = S.debug || {}, n = S.names;
    const col = (p, keys) => `<div class="dbg-side ${side(p)}"><small>${p === 1 ? 'PLAYER 1 CARRIAGE' : 'AI-SIDE CARRIAGE'}</small>
      <div class="dbg-keys">${keys}</div><div class="dbg-last">${esc(d[p] || '—')}</div></div>`;
    return ['debug' + d[1] + d[2], `<div class="debug"><div class="dbg-title">MOTOR &amp; STRIKER TEST</div>
      <div class="dbg-cols">
        ${col(1, 'JOYSTICK 1 · <b>A</b> ◀ &nbsp;<b>D</b> ▶ &nbsp;<b>W</b> STRIKE &nbsp;<b>S</b> STOP')}
        ${col(2, 'JOYSTICK 2 · <b>←</b> ◀ &nbsp;<b>→</b> ▶ &nbsp;<b>↑</b> STRIKE &nbsp;<b>↓</b> STOP')}
      </div>
      <div class="dbg-hint">Wrong way? Settings › Camera &amp; AI › Swap L/R &nbsp;·&nbsp; hold a joystick down 1 s or press Q to go back</div></div>`];
  }
  if (sc === 'pause') return ['pause', `<div class="dim"></div><div class="pause"><div class="question">Paused</div>
    ${S.menu.items.map((it, i) => `<div class="item" data-i="${i}">${esc(it.label)}</div>`).join('')}</div>`];
  return ['none', ''];
}

// ------------------------------------------------------------------ render
function render() {
  const sc = S.screen, inMatch = MATCH.includes(sc);
  document.body.classList.toggle('match-on', inMatch);
  document.body.classList.toggle('live-on', sc === 'live' || sc === 'countdown');
  document.body.classList.toggle('cal-on', sc === 'calibrate');
  $('match').classList.toggle('hidden', !inMatch);

  const screen = $('screen'), fn = SCREENS[sc];
  if (fn) {
    const [key, html, after] = fn();
    mount(screen, key, html);
    cursor(screen);
    after && after(screen);
  } else mount(screen, 'none', '');

  if (inMatch) updateMatch();
  const ov = $('overlay'), [k, h] = inMatch ? overlayFor() : ['none', ''];
  mount(ov, k, h);
  cursor(ov);
  const bb = $('buzz-bar');
  if (bb) bb.style.width = (100 * S.buzz.left / S.buzz.window) + '%';

  const cap = $('caption');
  cap.classList.toggle('off', !S.caption);
  if (S.caption) setText(cap.querySelector('.txt'), S.caption);
  cap.classList.toggle('no-skip', !!S.no_skip);

  if (!$('dev').classList.contains('hidden')) {
    setText($('lcd'), S.lcd.join('\n'));
    setText($('log'), S.log.join('\n'));
  }
}

(function loop() {
  if (innerWidth !== fit.w || innerHeight !== fit.h) { fit.w = innerWidth; fit.h = innerHeight; fit(); }
  if (S && MATCH.includes(S.screen)) Board.draw(S, scale);
  requestAnimationFrame(loop);
})();

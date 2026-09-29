// AI VISION: the table seen from above, with what the AI thinks on top of it (cm, as in config.py).
// Live game (state.video): the real camera picture (/video, the calibrated top-down view) with the
//   predicted path, the landing point and a ring on the ball drawn over it.
// Simulator: a drawn board. state.board = {ball, vel, path, path1 (player 1's AI), ai_x, p1_x}.
const Board = (() => {
  // board geometry (cm), sent by the laptop as state.arena (from config.py / calibration)
  let W = 44, H = 46, RAIL = [3, 41], DEPTH = 4, CW = 10, R = 2, SHAPE = [[3, 0], [41, 0], [41, 46], [3, 46]];
  let XL = 3, XR = 41, AI_Y = 6, P1_Y = 40, geomKey = '';
  function setGeom(a) {
    const k = JSON.stringify(a);
    if (!a || k === geomKey) return;
    geomKey = k;
    ({ w: W, h: H, rail: RAIL, depth: DEPTH, cw: CW, r: R, poly: SHAPE } = a);
    XL = Math.min(...SHAPE.map(p => p[0])); XR = Math.max(...SHAPE.map(p => p[0]));
    AI_Y = DEPTH + R; P1_Y = H - DEPTH - R;
    cv._scale = null;                        // re-fit
  }

  const cv = document.getElementById('board');
  let video = null;                         // the live camera stream (an <img> that keeps updating)
  function liveImage() {
    if (!video) {
      video = document.createElement('img');
      video.src = '/video';
      video.style.cssText = 'position:fixed;left:0;top:0;width:2px;height:2px;opacity:0.01;pointer-events:none';
      document.body.appendChild(video);
    }
    return video.naturalWidth ? video : null;
  }
  const ctx = cv.getContext('2d');
  let s = 18, ox = 0, oy = 0, last = performance.now();
  const trail = [];
  const sim = { x: W / 2, y: H / 2, vx: 18, vy: -34, ai: W / 2, p1: W / 2, trail: [] };

  function resize(scale) {
    const k = Math.min(2, (window.devicePixelRatio || 1) * scale);
    const w = cv.clientWidth, h = cv.clientHeight;
    if (!w) return;
    cv.width = Math.round(w * k); cv.height = Math.round(h * k);
    ctx.setTransform(k, 0, 0, k, 0, 0);
    s = Math.min((w - 200) / W, (h - 150) / H);
    ox = (w - W * s) / 2; oy = (h - H * s) / 2 + 8;
  }
  const px = (x, y) => [ox + x * s, oy + y * s];
  const clampC = x => Math.max(RAIL[0] + CW / 2, Math.min(RAIL[1] - CW / 2, x));

  function predict(x, y, vx, vy) {           // straight lines with side-wall bounces to the AI line
    const pts = [[x, y]];
    if (vy >= 0) return pts;
    for (let i = 0; i < 6; i++) {
      const tY = (AI_Y - y) / vy;
      const tX = vx > 0 ? (XR - R - x) / vx : vx < 0 ? (XL + R - x) / vx : Infinity;
      if (tY <= tX) { pts.push([x + vx * tY, AI_Y]); break; }
      x += vx * tX; y += vy * tX; vx = -vx; pts.push([x, y]);
    }
    return pts;
  }

  function stepSim(dt, st) {
    if (!st.running) {                       // ball waits in front of whoever restarts
      const top = st.placer === 2;
      sim.x += (W / 2 - sim.x) * 0.1; sim.y += ((top ? AI_Y + 3 : P1_Y - 3) - sim.y) * 0.1;
      sim.ai += (W / 2 - sim.ai) * 0.1; sim.p1 += (W / 2 - sim.p1) * 0.1;
      sim.trail = [];
      if (Math.abs(sim.vy) < 1) sim.vy = top ? 34 : -34;
      sim.vy = top ? Math.abs(sim.vy) : -Math.abs(sim.vy);
      return;
    }
    const fz = st.freeze || {};
    sim.x += sim.vx * dt; sim.y += sim.vy * dt;
    if (sim.x < XL + R) { sim.x = XL + R; sim.vx = Math.abs(sim.vx); }
    if (sim.x > XR - R) { sim.x = XR - R; sim.vx = -Math.abs(sim.vx); }
    if (sim.y < AI_Y) { sim.y = AI_Y; sim.vy = 28 + Math.random() * 16; sim.vx = (Math.random() - .5) * 50; }
    if (sim.y > P1_Y) { sim.y = P1_Y; sim.vy = -(28 + Math.random() * 16); sim.vx = (Math.random() - .5) * 50; }
    const tgt = predict(sim.x, sim.y, sim.vx, sim.vy).at(-1)[0];
    if (!(fz['2'] && fz['2'].frozen > 0)) sim.ai += Math.max(-40 * dt, Math.min(40 * dt, clampC(tgt) - sim.ai));
    if (!(fz['1'] && fz['1'].frozen > 0)) sim.p1 += Math.max(-30 * dt, Math.min(30 * dt, clampC(sim.x) - sim.p1));
    sim.trail.push([sim.x, sim.y]); if (sim.trail.length > 14) sim.trail.shift();
  }

  function carriage(x, top, color, frozen, t) {
    const y0 = top ? 0 : H - DEPTH;
    const [a, b] = px(x - CW / 2, y0), [c, d] = px(x + CW / 2, y0 + DEPTH);
    ctx.save();
    ctx.shadowColor = color; ctx.shadowBlur = 30;
    ctx.fillStyle = frozen ? '#bff4ff' : color;
    ctx.beginPath(); ctx.roundRect(a, b, c - a, d - b, 8); ctx.fill();
    ctx.restore();
    if (frozen) {                            // ice stripes
      ctx.save(); ctx.beginPath(); ctx.roundRect(a, b, c - a, d - b, 8); ctx.clip();
      ctx.strokeStyle = 'rgba(40,120,160,.55)'; ctx.lineWidth = 6;
      for (let k = -4; k < 14; k++) { const q = a + k * 22 + (t * 40 % 22); ctx.beginPath(); ctx.moveTo(q, d); ctx.lineTo(q + 40, b); ctx.stroke(); }
      ctx.restore();
    }
    // face line (where the striker hits)
    const fy = top ? d : b;
    ctx.fillStyle = 'rgba(255,255,255,.85)'; ctx.fillRect(a + 6, fy - (top ? 3 : 0), c - a - 12, 3);
  }

  function draw(st, scale) {
    const now = performance.now(), dt = Math.min(0.05, (now - last) / 1000), t = now / 1000;
    last = now;
    if (st) setGeom(st.arena);
    if (cv.width === 0 || cv._scale !== scale) { resize(scale); cv._scale = scale; }
    const real = st && st.board;
    if (!real && st) stepSim(dt, st);
    let b;
    if (real) {                              // the laptop's numbers, moved on smoothly between updates
      const age = Math.min(0.08, (now - (st._t || now)) / 1000), v = real.vel || [0, 0];
      const ball = real.ball && [real.ball[0] + v[0] * age, real.ball[1] + v[1] * age];
      if (ball && (v[0] || v[1])) { trail.push(ball); if (trail.length > 14) trail.shift(); } else trail.length = 0;
      b = { ...real, ball, trail };
    } else {
      b = { ball: [sim.x, sim.y], ai_x: sim.ai, p1_x: sim.p1, trail: sim.trail,
        path: st && st.running ? predict(sim.x, sim.y, sim.vx, sim.vy) : [] };
    }
    const w = cv.clientWidth, h = cv.clientHeight;
    ctx.clearRect(0, 0, w, h);
    const img = st && st.video ? liveImage() : null;

    if (img) {                               // the real table, straight from the camera
      ctx.save();
      ctx.beginPath(); ctx.roundRect(ox, oy, W * s, H * s, 10); ctx.clip();
      ctx.drawImage(img, ox, oy, W * s, H * s);
      ctx.fillStyle = 'rgba(4,8,16,.18)'; ctx.fillRect(ox, oy, W * s, H * s);   // a touch darker: overlays pop
      ctx.restore();
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(200,225,255,.35)';
      ctx.beginPath(); ctx.roundRect(ox, oy, W * s, H * s, 10); ctx.stroke();
    } else {
    // pitch
    ctx.save();
    ctx.beginPath(); SHAPE.forEach(([x, y], i) => { const [X, Y] = px(x, y); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); ctx.closePath();
    const g = ctx.createLinearGradient(0, oy, 0, oy + H * s);
    g.addColorStop(0, 'rgba(31,213,245,.10)'); g.addColorStop(.5, 'rgba(20,40,60,.25)'); g.addColorStop(1, 'rgba(255,91,46,.10)');
    ctx.fillStyle = g; ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(200,225,255,.55)'; ctx.stroke();
    ctx.clip();
    ctx.strokeStyle = 'rgba(255,255,255,.05)'; ctx.lineWidth = 1;          // grid, 2 cm
    for (let x = 0; x <= W; x += 2) { const [X] = px(x, 0); ctx.beginPath(); ctx.moveTo(X, oy); ctx.lineTo(X, oy + H * s); ctx.stroke(); }
    for (let y = 0; y <= H; y += 2) { const [, Y] = px(0, y); ctx.beginPath(); ctx.moveTo(ox, Y); ctx.lineTo(ox + W * s, Y); ctx.stroke(); }
    const [, my] = px(0, H / 2);                                            // halfway line + circle
    ctx.strokeStyle = 'rgba(255,255,255,.18)'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(ox, my); ctx.lineTo(ox + W * s, my); ctx.stroke();
    ctx.beginPath(); ctx.arc(ox + W / 2 * s, my, 6 * s, 0, 7); ctx.stroke();
    ctx.setLineDash([10, 10]); ctx.strokeStyle = 'rgba(31,213,245,.3)';    // strike lines
    let [, ly] = px(0, AI_Y); ctx.beginPath(); ctx.moveTo(ox, ly); ctx.lineTo(ox + W * s, ly); ctx.stroke();
    ctx.strokeStyle = 'rgba(255,91,46,.3)';
    [, ly] = px(0, P1_Y); ctx.beginPath(); ctx.moveTo(ox, ly); ctx.lineTo(ox + W * s, ly); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
    }

    const fz = (st && st.freeze) || {};
    if (img) {                               // real carriages are in the picture: mark them, ice when frozen
      [[b.ai_x, true, '#1fd5f5', fz['2']], [b.p1_x, false, '#ff5b2e', fz['1']]].forEach(([x, top, col, f]) => {
        if (x == null) return;
        const [a, y0] = px(x - CW / 2, top ? 0 : H - DEPTH), [c, y1] = px(x + CW / 2, top ? DEPTH : H);
        ctx.save();
        ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.shadowColor = col; ctx.shadowBlur = 14;
        ctx.strokeRect(a, y0, c - a, y1 - y0);
        if (f && f.frozen > 0) { ctx.fillStyle = 'rgba(190,240,255,.45)'; ctx.fillRect(a, y0, c - a, y1 - y0); }
        ctx.restore();
      });
    } else {
      carriage(b.ai_x ?? W / 2, true, '#1fd5f5', fz['2'] && fz['2'].frozen > 0, t);
      if (b.p1_x != null) carriage(b.p1_x, false, '#ff5b2e', fz['1'] && fz['1'].frozen > 0, t);
    }

    // predicted paths + landing reticles: the AI's (cool), and player 1's AI in AI vs AI (warm)
    [[b.path, '#1fd5f5'], [b.path1, '#ff5b2e']].forEach(([path, col]) => {
      if (!path || path.length < 2) return;
      ctx.save();
      ctx.setLineDash([16, 12]); ctx.lineDashOffset = -t * 60;
      ctx.strokeStyle = col; ctx.lineWidth = 4; ctx.shadowColor = col; ctx.shadowBlur = 16;
      ctx.beginPath(); path.forEach(([x, y], i) => { const [X, Y] = px(x, y); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); ctx.stroke();
      ctx.setLineDash([]);
      const [X, Y] = px(...path.at(-1)), r = 22 + Math.sin(t * 8) * 4;
      ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(X, Y, r, 0, 7); ctx.stroke();
      for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2 + t; ctx.beginPath(); ctx.moveTo(X + Math.cos(a) * (r + 4), Y + Math.sin(a) * (r + 4)); ctx.lineTo(X + Math.cos(a) * (r + 14), Y + Math.sin(a) * (r + 14)); ctx.stroke(); }
      ctx.restore();
    });

    // ball + trail
    (b.trail || []).forEach(([x, y], i, a) => {
      const [X, Y] = px(x, y); ctx.fillStyle = `rgba(255,190,90,${(i / a.length) * .35})`;
      ctx.beginPath(); ctx.arc(X, Y, R * s * (0.4 + i / a.length * 0.5), 0, 7); ctx.fill();
    });
    if (b.ball && img) {                     // the real ball is in the picture: a ring around it
      const [X, Y] = px(...b.ball);
      ctx.save(); ctx.strokeStyle = '#ffd08a'; ctx.lineWidth = 3; ctx.shadowColor = '#ffb347'; ctx.shadowBlur = 18;
      ctx.beginPath(); ctx.arc(X, Y, R * s + 8, 0, 7); ctx.stroke();
      ctx.restore();
    } else if (b.ball) {
      const [X, Y] = px(...b.ball);
      ctx.save(); ctx.shadowColor = '#ffb347'; ctx.shadowBlur = 30;
      const rg = ctx.createRadialGradient(X - 8, Y - 8, 2, X, Y, R * s);
      rg.addColorStop(0, '#fff3dc'); rg.addColorStop(.5, '#ffab3d'); rg.addColorStop(1, '#e0620f');
      ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(X, Y, R * s, 0, 7); ctx.fill();
      ctx.restore();
    }
  }
  return { draw };
})();

/**
 * DDL Pressure Radar — cyberpunk HUD.
 * Plots each non-closed task as a blip on a polar grid:
 *   - angle  = assigned main_person (stable alphabetical sector)
 *   - radius = DDL urgency (center = overdue/today, edge = 14d+)
 *   - color  = status
 * A sweep arm rotates and pings blips as it crosses them; overdue blips pulse.
 */
const TrackerRadar = (() => {
  const STATUS_COLOR = {
    in_progress:        '#FBBF24',
    completed_ready_qc: '#38BDF8',
    has_issues:         '#FB7185',
    pending:            '#94A3B8',
  };
  const STATUS_LABEL = {
    in_progress:        '搬砖中',
    completed_ready_qc: '待 QC',
    has_issues:         '有坑',
    pending:            '暂缓',
  };

  let _canvas = null;
  let _ctx = null;
  let _blips = [];
  let _sectors = [];
  let _rafId = null;
  let _sweep = 0;
  let _hoverBlip = null;
  let _onPick = null;
  let _ro = null;
  let _mouseMove = null;
  let _mouseLeave = null;
  let _click = null;

  function classify(t) {
    const q = t.qc_status || '';
    const m = t.main_status || '';
    if (q === '关闭问题') return null;
    if (q === '有问题，请修改') return 'has_issues';
    if (q === '待定，请留意') return 'pending';
    if (m === '已完成，可以QC') return 'completed_ready_qc';
    return 'in_progress';
  }

  function daysUntil(ddl) {
    if (!ddl) return null;
    const d = new Date(ddl);
    if (isNaN(d)) return null;
    d.setHours(0, 0, 0, 0);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return Math.round((d - today) / 86400000);
  }

  function buildBlips(tasks) {
    const valid = [];
    const personCounts = {};
    for (const t of tasks || []) {
      const cls = classify(t);
      if (!cls) continue;
      const days = daysUntil(t.ddl);
      if (days === null) continue;      // skip no-DDL tasks
      if (days > 30) continue;           // >30 days = off radar
      const person = t.main_person || '未分配';
      valid.push({ task: t, cls, days, person });
      personCounts[person] = (personCounts[person] || 0) + 1;
    }

    const persons = Object.keys(personCounts).sort();
    const step = (Math.PI * 2) / Math.max(persons.length, 1);
    const personAngle = {};
    persons.forEach((p, i) => { personAngle[p] = i * step - Math.PI / 2; });

    const sectors = persons.map(p => ({ person: p, angle: personAngle[p], count: personCounts[p] }));

    const subIdx = {};
    const blips = valid.map(v => {
      subIdx[v.person] = (subIdx[v.person] || 0) + 1;
      const i = subIdx[v.person] - 1;
      const n = personCounts[v.person];
      // Spread within the person's sector; for n=1 sit at center
      const sub = n === 1 ? 0 : -step * 0.35 + (step * 0.7) * (i / (n - 1));
      const angle = personAngle[v.person] + sub;
      // radius: -7d → 0 (center), +14d → 1 (edge). Clamp outside.
      const clamped = Math.max(-7, Math.min(v.days, 14));
      const radius = (clamped + 7) / 21;
      return { ...v, angle, radius };
    });

    return { blips, sectors };
  }

  function fitCanvas() {
    if (!_canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = _canvas.getBoundingClientRect();
    _canvas.width  = Math.max(1, rect.width  * dpr);
    _canvas.height = Math.max(1, rect.height * dpr);
    _ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function isDark() {
    return document.documentElement.classList.contains('dark');
  }

  function draw() {
    if (!_canvas || !_ctx) return;
    const rect = _canvas.getBoundingClientRect();
    const w = rect.width, h = rect.height;
    const cx = w / 2;
    const cy = h / 2;
    const R = Math.min(w, h) / 2 - 14;
    if (R <= 20) { _rafId = requestAnimationFrame(draw); return; }

    _ctx.clearRect(0, 0, w, h);
    const dark = isDark();

    if (_blips.length === 0) {
      _ctx.fillStyle = dark ? 'rgba(180,192,220,0.55)' : 'rgba(71,85,105,0.75)';
      _ctx.font = 'bold 12px "JetBrains Mono", Menlo, monospace';
      _ctx.textAlign = 'center';
      _ctx.textBaseline = 'middle';
      _ctx.fillText('// 无 DDL 任务 · 雷达静默', cx, cy);
      _rafId = requestAnimationFrame(draw);
      return;
    }

    // Concentric rings
    _ctx.lineWidth = 1;
    const ringColor = dark ? 'rgba(6,182,212,0.16)' : 'rgba(8,145,178,0.18)';
    const ringHot   = dark ? 'rgba(255,46,99,0.35)' : 'rgba(244,63,94,0.35)';
    [0.33, 0.66, 1.0].forEach((r, i) => {
      _ctx.strokeStyle = i === 0 ? ringHot : ringColor;
      _ctx.setLineDash(i === 0 ? [2, 3] : []);
      _ctx.beginPath();
      _ctx.arc(cx, cy, R * r, 0, Math.PI * 2);
      _ctx.stroke();
    });
    _ctx.setLineDash([]);

    // Sector dividers (one per person)
    if (_sectors.length > 1) {
      const step = (Math.PI * 2) / _sectors.length;
      _ctx.strokeStyle = dark ? 'rgba(148,163,184,0.08)' : 'rgba(100,116,139,0.12)';
      for (let i = 0; i < _sectors.length; i++) {
        const a = _sectors[i].angle - step / 2;
        _ctx.beginPath();
        _ctx.moveTo(cx, cy);
        _ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
        _ctx.stroke();
      }
    }

    // Person labels around the rim
    _ctx.font = '10px "JetBrains Mono", Menlo, monospace';
    _ctx.fillStyle = dark ? 'rgba(180,192,220,0.7)' : 'rgba(71,85,105,0.8)';
    _ctx.textAlign = 'center';
    _ctx.textBaseline = 'middle';
    for (const s of _sectors) {
      const lx = cx + Math.cos(s.angle) * (R + 8);
      const ly = cy + Math.sin(s.angle) * (R + 8);
      _ctx.fillText(s.person, lx, ly);
    }

    // Sweep trail (fading arcs behind the arm)
    _ctx.save();
    _ctx.translate(cx, cy);
    const trailSteps = 24;
    for (let i = 1; i <= trailSteps; i++) {
      const a0 = _sweep - (i * 0.04);
      const a1 = _sweep - ((i - 1) * 0.04);
      _ctx.strokeStyle = `rgba(6,182,212,${0.10 * (1 - i / trailSteps)})`;
      _ctx.lineWidth = 2;
      _ctx.beginPath();
      _ctx.arc(0, 0, R, a0, a1);
      _ctx.stroke();
    }
    // Main arm
    _ctx.strokeStyle = 'rgba(127,243,255,0.85)';
    _ctx.lineWidth = 1.5;
    _ctx.shadowColor = 'rgba(6,182,212,0.9)';
    _ctx.shadowBlur = 10;
    _ctx.beginPath();
    _ctx.moveTo(0, 0);
    _ctx.lineTo(Math.cos(_sweep) * R, Math.sin(_sweep) * R);
    _ctx.stroke();
    _ctx.restore();

    // Center dot (you-are-here = "NOW")
    _ctx.shadowColor = 'rgba(255,46,99,0.8)';
    _ctx.shadowBlur = 10;
    _ctx.fillStyle = '#FF2E63';
    _ctx.beginPath();
    _ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
    _ctx.fill();
    _ctx.shadowBlur = 0;

    // Ring labels
    _ctx.font = 'bold 9px "JetBrains Mono", Menlo, monospace';
    _ctx.fillStyle = dark ? 'rgba(127,243,255,0.55)' : 'rgba(14,116,144,0.7)';
    _ctx.textAlign = 'left';
    _ctx.fillText('NOW', cx + 5, cy - 2);
    _ctx.fillText('+7d', cx + R * 0.66 + 3, cy - 2);
    _ctx.fillText('+14d', cx + R - 20, cy - 2);

    // Blips
    const now = performance.now();
    for (const b of _blips) {
      const bx = cx + Math.cos(b.angle) * b.radius * R;
      const by = cy + Math.sin(b.angle) * b.radius * R;

      // Ping when sweep arm crosses blip
      const diff = ((b.angle - _sweep) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2);
      const nearSweep = Math.min(diff, Math.PI * 2 - diff);
      const ping = nearSweep < 0.25 ? 1 - nearSweep / 0.25 : 0;

      // Overdue pulse
      const overdue = b.days < 0 ? 0.4 + 0.4 * Math.abs(Math.sin(now * 0.005)) : 0;

      const color = STATUS_COLOR[b.cls] || '#94A3B8';
      const isHover = _hoverBlip === b;
      const size = 3 + ping * 3 + overdue * 2 + (isHover ? 2 : 0);

      _ctx.fillStyle = color;
      _ctx.shadowColor = color;
      _ctx.shadowBlur = 6 + ping * 14 + (isHover ? 10 : 0) + overdue * 6;
      _ctx.beginPath();
      _ctx.arc(bx, by, size, 0, Math.PI * 2);
      _ctx.fill();

      // Outline
      _ctx.shadowBlur = 0;
      _ctx.strokeStyle = isHover ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.25)';
      _ctx.lineWidth = isHover ? 1.5 : 0.75;
      _ctx.stroke();

      b._x = bx; b._y = by; b._hit = Math.max(size + 2, 7);
    }
    _ctx.shadowBlur = 0;

    _sweep += 0.018;
    if (_sweep > Math.PI * 2) _sweep -= Math.PI * 2;
    _rafId = requestAnimationFrame(draw);
  }

  function hitTest(mx, my) {
    let found = null, bestD = Infinity;
    for (const b of _blips) {
      if (b._x == null) continue;
      const dx = b._x - mx, dy = b._y - my;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d <= b._hit && d < bestD) { bestD = d; found = b; }
    }
    return found;
  }

  function showTooltip(blip, clientX, clientY) {
    let el = document.getElementById('cfx-chart-tt');
    if (!el) {
      el = document.createElement('div');
      el.id = 'cfx-chart-tt';
      el.className = 'cfx-chart-tt';
      document.body.appendChild(el);
    }
    const daysTxt = blip.days < 0 ? `逾期 ${-blip.days}d` : blip.days === 0 ? '今日截止' : `剩 ${blip.days}d`;
    const nameRaw = blip.task.item_name || blip.task.task_name || '—';
    const name = nameRaw.length > 40 ? nameRaw.slice(0, 40) + '…' : nameRaw;
    const color = STATUS_COLOR[blip.cls];
    el.innerHTML =
      `<div class="cfx-chart-tt__title">${blip.person} · ${STATUS_LABEL[blip.cls] || ''}</div>` +
      `<div class="cfx-chart-tt__row"><span class="cfx-chart-tt__dot" style="background:${color};box-shadow:0 0 6px ${color}"></span>${name}</div>` +
      `<div class="cfx-chart-tt__row" style="color:${blip.days < 0 ? '#FB7185' : '#7FF3FF'}">◷ ${daysTxt} · DDL ${blip.task.ddl}</div>`;
    el.style.opacity = 1;
    el.style.left = (clientX + window.scrollX) + 'px';
    el.style.top  = (clientY + window.scrollY) + 'px';
    el.style.borderColor = color;
    el.style.boxShadow = `0 0 0 1px ${color}33, 0 8px 24px -8px ${color}80`;
  }
  function hideTooltip() {
    const el = document.getElementById('cfx-chart-tt');
    if (el) el.style.opacity = 0;
  }

  function destroy() {
    if (_rafId) cancelAnimationFrame(_rafId);
    if (_ro && _canvas) _ro.unobserve(_canvas);
    if (_canvas && _mouseMove) _canvas.removeEventListener('mousemove', _mouseMove);
    if (_canvas && _mouseLeave) _canvas.removeEventListener('mouseleave', _mouseLeave);
    if (_canvas && _click) _canvas.removeEventListener('click', _click);
    _rafId = null; _canvas = null; _ctx = null; _blips = []; _sectors = []; _hoverBlip = null;
    hideTooltip();
  }

  function init(canvasId, tasks, opts) {
    opts = opts || {};
    const el = document.getElementById(canvasId);
    if (!el) return;
    destroy();
    _canvas = el;
    _ctx = el.getContext('2d');
    _onPick = opts.onPick || null;

    const { blips, sectors } = buildBlips(tasks);
    _blips = blips;
    _sectors = sectors;

    fitCanvas();
    if (window.ResizeObserver) {
      _ro = new ResizeObserver(fitCanvas);
      _ro.observe(_canvas);
    }

    _mouseMove = (e) => {
      const rect = _canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const hit = hitTest(mx, my);
      _hoverBlip = hit;
      _canvas.style.cursor = hit ? 'pointer' : 'crosshair';
      if (hit) showTooltip(hit, e.clientX + 12, e.clientY - 12);
      else hideTooltip();
    };
    _mouseLeave = () => { _hoverBlip = null; hideTooltip(); _canvas.style.cursor = 'default'; };
    _click = () => { if (_hoverBlip && _onPick) _onPick(_hoverBlip.task, _hoverBlip); };
    _canvas.addEventListener('mousemove', _mouseMove);
    _canvas.addEventListener('mouseleave', _mouseLeave);
    _canvas.addEventListener('click', _click);

    _rafId = requestAnimationFrame(draw);
  }

  return { init, destroy };
})();

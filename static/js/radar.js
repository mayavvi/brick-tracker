/**
 * DDL Pressure Radar.
 * Static pressure zones show urgency by radius:
 * center <=3d, middle <=7d, outer <=14d. Task dots share one color.
 */
const TrackerRadar = (() => {
  const MAX_RADAR_DAYS = 14;
  const TASK_COLOR = "#2E9279";
  const PRESSURE_ZONES = [
    { limit: 3, radius: 0.36, fill: "rgba(244, 63, 94, 0.20)", stroke: "rgba(190, 18, 60, 0.28)", label: "3D" },
    { limit: 7, radius: 0.68, fill: "rgba(245, 158, 11, 0.14)", stroke: "rgba(180, 83, 9, 0.22)", label: "7D" },
    { limit: 14, radius: 1.00, fill: "rgba(46, 146, 121, 0.12)", stroke: "rgba(32, 95, 81, 0.20)", label: "14D" },
  ];

  const STATUS_LABEL = {
    in_progress: "搬砖中",
    completed_ready_qc: "待 QC",
    has_issues: "有坑",
    pending: "暂缓",
  };

  let _canvas = null;
  let _ctx = null;
  let _blips = [];
  let _sectors = [];
  let _rafId = null;
  let _hoverBlip = null;
  let _onPick = null;
  let _ro = null;
  let _mouseMove = null;
  let _mouseLeave = null;
  let _click = null;

  function classify(t) {
    const q = t.qc_status || "";
    const m = t.main_status || "";
    if (q === "关闭问题") return null;
    if (q === "有问题，请修改") return "has_issues";
    if (q === "待定，请留意") return "pending";
    if (m === "已完成，可以QC") return "completed_ready_qc";
    return "in_progress";
  }

  function daysUntil(ddl) {
    if (!ddl) return null;
    const d = new Date(ddl);
    if (isNaN(d)) return null;
    d.setHours(0, 0, 0, 0);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((d - today) / 86400000);
  }

  function radiusForDays(days) {
    if (days <= 3) return 0.18 + Math.max(days, 0) / 3 * 0.18;
    if (days <= 7) return 0.38 + (days - 3) / 4 * 0.28;
    return 0.70 + (days - 7) / 7 * 0.28;
  }

  function buildBlips(tasks) {
    const valid = [];
    const personCounts = {};
    for (const t of tasks || []) {
      const cls = classify(t);
      if (!cls) continue;
      const days = daysUntil(t.ddl);
      if (days === null) continue;
      if (days > MAX_RADAR_DAYS) continue;
      const person = t.main_person || t.qc_person || "未分配";
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
      const sub = n === 1 ? 0 : -step * 0.32 + (step * 0.64) * (i / (n - 1));
      return {
        ...v,
        angle: personAngle[v.person] + sub,
        radius: radiusForDays(v.days),
      };
    });

    return { blips, sectors };
  }

  function fitCanvas() {
    if (!_canvas || !_ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = _canvas.getBoundingClientRect();
    _canvas.width = Math.max(1, rect.width * dpr);
    _canvas.height = Math.max(1, rect.height * dpr);
    _ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function drawPressureZones(cx, cy, R) {
    for (let i = PRESSURE_ZONES.length - 1; i >= 0; i--) {
      const z = PRESSURE_ZONES[i];
      _ctx.fillStyle = z.fill;
      _ctx.strokeStyle = z.stroke;
      _ctx.lineWidth = 1;
      _ctx.beginPath();
      _ctx.arc(cx, cy, R * z.radius, 0, Math.PI * 2);
      _ctx.fill();
      _ctx.stroke();
    }

    _ctx.font = 'bold 9px "JetBrains Mono", Menlo, monospace';
    _ctx.fillStyle = "rgba(68, 64, 60, 0.58)";
    _ctx.textAlign = "center";
    _ctx.textBaseline = "middle";
    for (const z of PRESSURE_ZONES) {
      _ctx.fillText(z.label, cx, cy - R * z.radius + 11);
    }
  }

  function draw() {
    if (!_canvas || !_ctx) return;
    const rect = _canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const cx = w / 2;
    const cy = h / 2;
    const R = Math.min(w, h) / 2 - 18;
    if (R <= 20) {
      _rafId = requestAnimationFrame(draw);
      return;
    }

    _ctx.clearRect(0, 0, w, h);

    if (_blips.length === 0) {
      drawPressureZones(cx, cy, R);
      _ctx.fillStyle = "rgba(87, 83, 78, 0.74)";
      _ctx.font = '700 12px "Segoe UI", "Microsoft YaHei", sans-serif';
      _ctx.textAlign = "center";
      _ctx.textBaseline = "middle";
      _ctx.fillText("14 天内暂无 DDL 压力", cx, cy);
      _rafId = requestAnimationFrame(draw);
      return;
    }

    drawPressureZones(cx, cy, R);

    if (_sectors.length > 1) {
      const step = (Math.PI * 2) / _sectors.length;
      _ctx.strokeStyle = "rgba(87, 83, 78, 0.10)";
      for (let i = 0; i < _sectors.length; i++) {
        const a = _sectors[i].angle - step / 2;
        _ctx.beginPath();
        _ctx.moveTo(cx, cy);
        _ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
        _ctx.stroke();
      }
    }

    _ctx.font = '10px "Segoe UI", "Microsoft YaHei", sans-serif';
    _ctx.fillStyle = "rgba(68, 64, 60, 0.78)";
    _ctx.textAlign = "center";
    _ctx.textBaseline = "middle";
    for (const s of _sectors) {
      const lx = cx + Math.cos(s.angle) * (R + 10);
      const ly = cy + Math.sin(s.angle) * (R + 10);
      _ctx.fillText(s.person, lx, ly);
    }

    const now = performance.now();
    for (const b of _blips) {
      const bx = cx + Math.cos(b.angle) * b.radius * R;
      const by = cy + Math.sin(b.angle) * b.radius * R;
      const urgentPulse = b.days <= 3 ? 0.5 + 0.5 * Math.abs(Math.sin(now * 0.004)) : 0.25 + 0.25 * Math.abs(Math.sin(now * 0.003));
      const isHover = _hoverBlip === b;
      const size = 4 + urgentPulse * 1.6 + (isHover ? 2 : 0);

      _ctx.fillStyle = TASK_COLOR;
      _ctx.shadowColor = TASK_COLOR;
      _ctx.shadowBlur = 6 + urgentPulse * 8 + (isHover ? 8 : 0);
      _ctx.beginPath();
      _ctx.arc(bx, by, size, 0, Math.PI * 2);
      _ctx.fill();
      _ctx.shadowBlur = 0;

      _ctx.strokeStyle = isHover ? "rgba(255, 253, 248, 0.95)" : "rgba(255, 253, 248, 0.72)";
      _ctx.lineWidth = isHover ? 1.6 : 1;
      _ctx.stroke();

      b._x = bx;
      b._y = by;
      b._hit = Math.max(size + 3, 8);
    }

    _rafId = requestAnimationFrame(draw);
  }

  function hitTest(mx, my) {
    let found = null;
    let bestD = Infinity;
    for (const b of _blips) {
      if (b._x == null) continue;
      const dx = b._x - mx;
      const dy = b._y - my;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d <= b._hit && d < bestD) {
        bestD = d;
        found = b;
      }
    }
    return found;
  }

  function showTooltip(blip, clientX, clientY) {
    let el = document.getElementById("cfx-chart-tt");
    if (!el) {
      el = document.createElement("div");
      el.id = "cfx-chart-tt";
      el.className = "cfx-chart-tt";
      document.body.appendChild(el);
    }
    const daysTxt = blip.days < 0 ? `逾期 ${-blip.days}d` : blip.days === 0 ? "今日截止" : `剩 ${blip.days}d`;
    const nameRaw = blip.task.item_name || blip.task.task_name || "-";
    const name = nameRaw.length > 40 ? nameRaw.slice(0, 40) + "..." : nameRaw;
    el.innerHTML =
      `<div class="cfx-chart-tt__title">${blip.person} · ${STATUS_LABEL[blip.cls] || ""}</div>` +
      `<div class="cfx-chart-tt__row"><span class="cfx-chart-tt__dot" style="background:${TASK_COLOR};box-shadow:0 0 6px ${TASK_COLOR}"></span>${name}</div>` +
      `<div class="cfx-chart-tt__row" style="color:${blip.days <= 3 ? "#BE123C" : "#205F51"}">DDL ${blip.task.ddl} · ${daysTxt}</div>`;
    el.style.opacity = 1;
    el.style.left = (clientX + window.scrollX) + "px";
    el.style.top = (clientY + window.scrollY) + "px";
    el.style.borderColor = TASK_COLOR;
    el.style.boxShadow = `0 0 0 1px ${TASK_COLOR}33, 0 12px 28px -16px ${TASK_COLOR}99`;
  }

  function hideTooltip() {
    const el = document.getElementById("cfx-chart-tt");
    if (el) el.style.opacity = 0;
  }

  function destroy() {
    if (_rafId) cancelAnimationFrame(_rafId);
    if (_ro && _canvas) _ro.unobserve(_canvas);
    if (_canvas && _mouseMove) _canvas.removeEventListener("mousemove", _mouseMove);
    if (_canvas && _mouseLeave) _canvas.removeEventListener("mouseleave", _mouseLeave);
    if (_canvas && _click) _canvas.removeEventListener("click", _click);
    _rafId = null;
    _canvas = null;
    _ctx = null;
    _blips = [];
    _sectors = [];
    _hoverBlip = null;
    hideTooltip();
  }

  function init(canvasId, tasks, opts) {
    opts = opts || {};
    const el = document.getElementById(canvasId);
    if (!el) return;
    destroy();
    _canvas = el;
    _ctx = el.getContext("2d");
    _onPick = opts.onPick || null;

    const built = buildBlips(tasks);
    _blips = built.blips;
    _sectors = built.sectors;

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
      _canvas.style.cursor = hit ? "pointer" : "default";
      if (hit) showTooltip(hit, e.clientX + 12, e.clientY - 12);
      else hideTooltip();
    };
    _mouseLeave = () => {
      _hoverBlip = null;
      hideTooltip();
      _canvas.style.cursor = "default";
    };
    _click = () => {
      if (_hoverBlip && _onPick) _onPick(_hoverBlip.task, _hoverBlip);
    };
    _canvas.addEventListener("mousemove", _mouseMove);
    _canvas.addEventListener("mouseleave", _mouseLeave);
    _canvas.addEventListener("click", _click);

    _rafId = requestAnimationFrame(draw);
  }

  return { init, destroy };
})();

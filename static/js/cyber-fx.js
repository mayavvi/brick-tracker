/**
 * Cyber FX — particles, count-up, tilt, glitch, boot sequence.
 * Attached to window.CyberFX. Zero deps.
 */
(function () {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ==================== Particle field ====================
  function initParticles(canvas) {
    if (!canvas || reducedMotion) return;
    const ctx = canvas.getContext('2d');
    let W = 0, H = 0, parts = [];
    const DPR = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    function make() {
      const count = Math.min(70, Math.floor((W * H) / 26000));
      parts = [];
      for (let i = 0; i < count; i++) {
        parts.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.15,
          vy: -0.05 - Math.random() * 0.25,
          r: 0.6 + Math.random() * 1.6,
          hue: Math.random() < 0.5 ? 188 : 290,
          a: 0.25 + Math.random() * 0.5,
        });
      }
    }
    function step() {
      ctx.clearRect(0, 0, W, H);
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy;
        if (p.y < -5)   { p.y = H + 5; p.x = Math.random() * W; }
        if (p.x < -5)   p.x = W + 5;
        if (p.x > W+5)  p.x = -5;
        ctx.beginPath();
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 6);
        g.addColorStop(0, `hsla(${p.hue}, 95%, 65%, ${p.a})`);
        g.addColorStop(1, `hsla(${p.hue}, 95%, 65%, 0)`);
        ctx.fillStyle = g;
        ctx.arc(p.x, p.y, p.r * 6, 0, Math.PI * 2);
        ctx.fill();
      }
      requestAnimationFrame(step);
    }
    resize(); make();
    window.addEventListener('resize', () => { resize(); make(); });
    requestAnimationFrame(step);
  }

  // ==================== Count-up ====================
  function countUp(el, target, duration) {
    if (!el) return;
    target = Number(target) || 0;
    duration = duration || 650;
    if (reducedMotion) { el.textContent = target; return; }
    const from = Number(el.dataset.cfxFrom || 0);
    const t0 = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = Math.round(from + (target - from) * eased);
      el.textContent = v;
      if (p < 1) requestAnimationFrame(tick);
      else el.dataset.cfxFrom = target;
    }
    requestAnimationFrame(tick);
  }

  // ==================== 3D tilt ====================
  function bindTilt(el, max) {
    if (!el || reducedMotion) return;
    max = max || 6;
    let rect = null;
    function enter() { rect = el.getBoundingClientRect(); el.style.transition = 'transform 120ms ease'; }
    function move(e) {
      if (!rect) rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = (e.clientX - cx) / (rect.width / 2);
      const dy = (e.clientY - cy) / (rect.height / 2);
      el.style.transform = `perspective(700px) rotateX(${(-dy * max).toFixed(2)}deg) rotateY(${(dx * max).toFixed(2)}deg) translateZ(4px)`;
    }
    function leave() { el.style.transform = ''; rect = null; }
    el.addEventListener('mouseenter', enter);
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', leave);
  }

  // Auto-bind via data attribute
  function autoTilt(root) {
    (root || document).querySelectorAll('[data-cfx-tilt]').forEach(el => {
      if (el.dataset.cfxTiltBound) return;
      el.dataset.cfxTiltBound = '1';
      bindTilt(el, Number(el.dataset.cfxTilt) || 6);
    });
  }

  // ==================== Boot sequence ====================
  function bootSequence(lines, onDone) {
    if (reducedMotion) { onDone && onDone(); return; }
    const overlay = document.createElement('div');
    overlay.className = 'cfx-boot';
    overlay.innerHTML = `
      <div class="cfx-boot-frame">
        <div class="cfx-boot-top">
          <span class="cfx-boot-dot"></span>
          <span class="cfx-boot-dot" style="animation-delay:.15s"></span>
          <span class="cfx-boot-dot" style="animation-delay:.3s"></span>
          <span class="cfx-boot-head">PEAK // BOOT</span>
        </div>
        <div class="cfx-boot-body"></div>
      </div>`;
    document.body.appendChild(overlay);
    const body = overlay.querySelector('.cfx-boot-body');
    let i = 0;
    function next() {
      if (i >= lines.length) {
        setTimeout(() => {
          overlay.classList.add('cfx-boot-out');
          setTimeout(() => { overlay.remove(); onDone && onDone(); }, 320);
        }, 260);
        return;
      }
      const row = document.createElement('div');
      row.className = 'cfx-boot-row';
      row.innerHTML = `<span class="cfx-boot-ok">[ OK ]</span> <span class="cfx-boot-msg"></span>`;
      body.appendChild(row);
      const msg = row.querySelector('.cfx-boot-msg');
      const str = lines[i++];
      let k = 0;
      (function type() {
        if (k <= str.length) {
          msg.textContent = str.slice(0, k++);
          setTimeout(type, 14 + Math.random() * 18);
        } else {
          setTimeout(next, 90);
        }
      })();
    }
    next();
  }

  // ==================== Glitch bind ====================
  function bindGlitch(root) {
    (root || document).querySelectorAll('[data-cfx-glitch]').forEach(el => {
      if (el.dataset.cfxGlitchBound) return;
      el.dataset.cfxGlitchBound = '1';
      const text = el.textContent;
      el.setAttribute('data-text', text);
      el.classList.add('cfx-glitch');
    });
  }

  // ==================== HUD clock/uptime ====================
  function initHudTicker(el) {
    if (!el) return;
    const start = Date.now();
    function pad(n) { return n < 10 ? '0' + n : '' + n; }
    function tick() {
      const d = new Date();
      const up = Math.floor((Date.now() - start) / 1000);
      const hh = pad(Math.floor(up / 3600));
      const mm = pad(Math.floor((up % 3600) / 60));
      const ss = pad(up % 60);
      const clk = pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
      el.textContent = `ONLINE · ${clk} · UP ${hh}:${mm}:${ss}`;
    }
    tick();
    setInterval(tick, 1000);
  }

  // ==================== Mouse spotlight ====================
  function bindSpotlight(el) {
    if (!el || reducedMotion) return;
    if (el.dataset.cfxSpotBound) return;
    el.dataset.cfxSpotBound = '1';
    el.classList.add('cfx-spotlight');
    el.addEventListener('mousemove', e => {
      const r = el.getBoundingClientRect();
      el.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100) + '%');
      el.style.setProperty('--my', ((e.clientY - r.top) / r.height * 100) + '%');
    });
  }
  function autoSpotlight(root) {
    (root || document).querySelectorAll('[data-cfx-spot]').forEach(bindSpotlight);
  }

  // ==================== Typewriter ====================
  function typewriter(el, text, speed) {
    if (!el) return;
    speed = speed || 22;
    if (reducedMotion) { el.textContent = text; return; }
    if (el._cfxTypeTimer) clearInterval(el._cfxTypeTimer);
    el.textContent = '';
    let i = 0;
    el._cfxTypeTimer = setInterval(() => {
      el.textContent = text.slice(0, ++i);
      if (i >= text.length) { clearInterval(el._cfxTypeTimer); el._cfxTypeTimer = null; }
    }, speed);
  }

  // ==================== Command palette ====================
  let _cmdState = null;
  function initCommandPalette(getActions) {
    if (_cmdState) return;
    const overlay = document.createElement('div');
    overlay.className = 'cfx-cmd hidden';
    overlay.innerHTML = `
      <div class="cfx-cmd-frame cfx-corners">
        <div class="cfx-cmd-header">
          <span class="cfx-cmd-prompt">⌘</span>
          <input type="text" class="cfx-cmd-input" placeholder="// 输入指令…例如 刷新 / 主题 / 工作台" />
          <span class="cfx-cmd-hint">ESC 关闭</span>
        </div>
        <div class="cfx-cmd-list"></div>
        <div class="cfx-cmd-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
          <span><kbd>↵</kbd> 执行</span>
          <span><kbd>ESC</kbd> 关闭</span>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector('.cfx-cmd-input');
    const list  = overlay.querySelector('.cfx-cmd-list');
    let actions = [];
    let filtered = [];
    let idx = 0;

    function render() {
      const q = input.value.trim().toLowerCase();
      filtered = !q ? actions.slice() : actions.filter(a =>
        (a.label + ' ' + (a.hint || '') + ' ' + (a.key || '')).toLowerCase().includes(q)
      );
      idx = Math.min(idx, Math.max(0, filtered.length - 1));
      list.innerHTML = filtered.length === 0
        ? '<div class="cfx-cmd-empty">// 无匹配指令 [ NO_MATCH ]</div>'
        : filtered.map((a, i) => `
          <div class="cfx-cmd-item ${i === idx ? 'is-active' : ''}" data-i="${i}">
            <span class="cfx-cmd-icon">${a.icon || '▸'}</span>
            <span class="cfx-cmd-lbl">${a.label}</span>
            <span class="cfx-cmd-hnt">${a.hint || ''}</span>
          </div>`).join('');
      list.querySelectorAll('.cfx-cmd-item').forEach(n => {
        n.addEventListener('mouseenter', () => { idx = Number(n.dataset.i); render(); });
        n.addEventListener('click', () => exec());
      });
    }
    function exec() {
      const a = filtered[idx];
      if (a && typeof a.run === 'function') { close(); setTimeout(a.run, 50); }
    }
    function open() {
      actions = (getActions && getActions()) || [];
      overlay.classList.remove('hidden');
      requestAnimationFrame(() => overlay.classList.add('cfx-cmd-in'));
      input.value = ''; idx = 0; render();
      setTimeout(() => input.focus(), 30);
    }
    function close() {
      overlay.classList.remove('cfx-cmd-in');
      setTimeout(() => overlay.classList.add('hidden'), 180);
    }

    input.addEventListener('input', render);
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(filtered.length-1, idx+1); render(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(0, idx-1); render(); }
      else if (e.key === 'Enter') { e.preventDefault(); exec(); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

    window.addEventListener('keydown', e => {
      const target = e.target;
      const isTyping = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        if (overlay.classList.contains('hidden')) open(); else close();
      } else if (!isTyping && e.key === 'k' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        // bare `k` also opens (helper)
        if (overlay.classList.contains('hidden')) { e.preventDefault(); open(); }
      }
    });

    _cmdState = { open, close };
    return _cmdState;
  }

  window.CyberFX = {
    initParticles, countUp, bindTilt, autoTilt,
    bootSequence, bindGlitch, initHudTicker,
    bindSpotlight, autoSpotlight, typewriter,
    initCommandPalette,
  };
})();

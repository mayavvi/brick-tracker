/**
 * Chart.js chart management for the tracker dashboard.
 * Provides donut (status), bar (person workload), and DDL timeline charts.
 */

const TrackerCharts = (() => {
  let _donut = null;
  let _bar = null;
  let _timeline = null;

  const STATUS_COLORS = {
    in_progress:        { bg: '#FBBF24', border: '#F59E0B', glow: 'rgba(251,191,36,0.5)' },
    completed_ready_qc: { bg: '#38BDF8', border: '#0EA5E9', glow: 'rgba(56,189,248,0.55)' },
    has_issues:         { bg: '#FB7185', border: '#F43F5E', glow: 'rgba(251,113,133,0.6)' },
    pending:            { bg: '#94A3B8', border: '#64748B', glow: 'rgba(148,163,184,0.35)' },
    closed:             { bg: '#34D399', border: '#10B981', glow: 'rgba(52,211,153,0.55)' },
  };

  const STATUS_LABELS = {
    in_progress: '搬砖中',
    completed_ready_qc: '待 QC',
    has_issues: '有坑',
    pending: '暂缓',
    closed: '归档',
  };

  function makeRadialGrad(ctx, cx, cy, r, color) {
    const g = ctx.createRadialGradient(cx, cy, r * 0.3, cx, cy, r);
    g.addColorStop(0, color);
    g.addColorStop(1, color.replace(/[\d.]+\)$/, '0.35)'));
    return g;
  }

  function isDark() {
    return document.documentElement.classList.contains('dark');
  }

  function textColor() {
    return isDark() ? '#B4C0DC' : '#334155';
  }

  function gridColor() {
    return isDark() ? 'rgba(6,182,212,0.12)' : 'rgba(100,116,139,0.18)';
  }

  /* External HTML tooltip — escapes canvas bounds, cyberpunk neon card.
     Placed at document.body so it can overflow the chart container. */
  function externalTooltip(ctx) {
    const { chart, tooltip } = ctx;
    let el = document.getElementById('cfx-chart-tt');
    if (!el) {
      el = document.createElement('div');
      el.id = 'cfx-chart-tt';
      el.className = 'cfx-chart-tt';
      document.body.appendChild(el);
    }
    if (tooltip.opacity === 0) { el.style.opacity = 0; return; }

    const title = (tooltip.title || []).join(' ');
    const lines = (tooltip.body || []).map(b => b.lines.join(' '));
    const accent = (tooltip.labelColors && tooltip.labelColors[0] && tooltip.labelColors[0].backgroundColor) || '#06B6D4';
    el.innerHTML =
      (title ? `<div class="cfx-chart-tt__title">${title}</div>` : '') +
      lines.map(l => `<div class="cfx-chart-tt__row"><span class="cfx-chart-tt__dot" style="background:${accent};box-shadow:0 0 6px ${accent}"></span>${l}</div>`).join('');

    const rect = chart.canvas.getBoundingClientRect();
    const x = rect.left + window.scrollX + tooltip.caretX;
    const y = rect.top  + window.scrollY + tooltip.caretY;
    el.style.opacity = 1;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
    el.style.borderColor = accent;
    el.style.boxShadow = `0 0 0 1px ${accent}33, 0 8px 24px -8px ${accent}80`;
  }

  function destroyAll() {
    if (_donut)    { _donut.destroy();    _donut = null; }
    if (_bar)      { _bar.destroy();      _bar = null; }
    if (_timeline) {
      if (_timeline._pulseInt) clearInterval(_timeline._pulseInt);
      _timeline.destroy(); _timeline = null;
    }
  }

  function initDonut(canvasId, summary) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (_donut) _donut.destroy();

    const keys   = Object.keys(STATUS_COLORS);
    const values = keys.map(k => summary[k] || 0);
    const total  = values.reduce((a, b) => a + b, 0);
    if (total === 0) { ctx.getContext('2d').clearRect(0, 0, ctx.width, ctx.height); return; }

    const closedPct = total > 0 ? Math.round(((summary.closed || 0) / total) * 100) : 0;

    const centerText = {
      id: 'centerText',
      afterDraw(chart) {
        const { ctx, chartArea: { left, right, top, bottom } } = chart;
        const cx = (left + right) / 2;
        const cy = (top + bottom) / 2;
        const dark = isDark();
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // Big total — larger, high-contrast, theme-aware
        ctx.shadowColor = dark ? 'rgba(6,182,212,0.75)' : 'rgba(8,145,178,0.35)';
        ctx.shadowBlur = dark ? 14 : 6;
        ctx.fillStyle = dark ? '#7FF3FF' : '#0E7490';
        ctx.font = 'bold 32px "JetBrains Mono", Menlo, monospace';
        ctx.fillText(total, cx, cy - 8);

        // Subtitle — bigger, better contrast in light mode
        ctx.shadowBlur = 0;
        ctx.fillStyle = dark ? '#94A3B8' : '#475569';
        ctx.font = 'bold 10px "JetBrains Mono", Menlo, monospace';
        ctx.fillText('TOTAL', cx, cy + 12);

        // Closed percent — accent line
        ctx.fillStyle = dark ? '#34D399' : '#059669';
        ctx.font = 'bold 11px "JetBrains Mono", Menlo, monospace';
        ctx.fillText('◆ ' + closedPct + '% DONE', cx, cy + 26);
        ctx.restore();
      }
    };

    const arcGlow = {
      id: 'arcGlow',
      beforeDatasetDraw(chart) {
        chart.ctx.save();
        chart.ctx.shadowColor = 'rgba(6,182,212,0.5)';
        chart.ctx.shadowBlur = 18;
      },
      afterDatasetDraw(chart) { chart.ctx.restore(); }
    };

    _donut = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: keys.map(k => STATUS_LABELS[k]),
        datasets: [{
          data: values,
          backgroundColor: keys.map(k => STATUS_COLORS[k].bg),
          borderColor: '#0A0E1A',
          borderWidth: 2,
          hoverOffset: 8,
          hoverBorderColor: keys.map(k => STATUS_COLORS[k].border),
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        layout: { padding: { top: 8, bottom: 4, left: 4, right: 4 } },
        animation: { animateRotate: true, duration: 900 },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: textColor(),
              font: { size: 10, family: '"JetBrains Mono", Menlo, monospace' },
              boxWidth: 8,
              boxHeight: 8,
              padding: 8,
              usePointStyle: true,
              pointStyle: 'rectRounded',
            }
          },
          tooltip: {
            enabled: false,
            external: externalTooltip,
            callbacks: {
              label: function(ctx) {
                const pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
                return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
              }
            }
          }
        }
      },
      plugins: [centerText, arcGlow],
    });
  }

  function initBar(canvasId, tasks) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (_bar) _bar.destroy();

    // Aggregate person workload
    const personMap = {};
    for (const t of tasks) {
      const persons = new Set();
      if (t.main_person) persons.add(t.main_person);
      if (t.qc_person)   persons.add(t.qc_person);
      for (const p of persons) {
        if (!personMap[p]) personMap[p] = { in_progress: 0, completed_ready_qc: 0, has_issues: 0, pending: 0, closed: 0 };
        const mainStatus = t.main_status || '';
        const qcStatus   = t.qc_status   || '';
        if (qcStatus === '关闭问题') personMap[p].closed++;
        else if (qcStatus === '有问题，请修改') personMap[p].has_issues++;
        else if (qcStatus === '待定，请留意') personMap[p].pending++;
        else if (mainStatus === '已完成，可以QC') personMap[p].completed_ready_qc++;
        else personMap[p].in_progress++;
      }
    }

    // Top 12 persons by total
    const persons = Object.entries(personMap)
      .map(([name, counts]) => ({ name, total: Object.values(counts).reduce((a,b)=>a+b,0), ...counts }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 12);

    if (persons.length === 0) return;

    const statusKeys = ['in_progress', 'completed_ready_qc', 'has_issues', 'pending', 'closed'];
    const datasets = statusKeys.map(k => ({
      label: STATUS_LABELS[k],
      data: persons.map(p => p[k] || 0),
      backgroundColor: STATUS_COLORS[k].bg,
      borderColor: STATUS_COLORS[k].border,
      borderWidth: 1,
      borderRadius: 4,
      borderSkipped: false,
      hoverBackgroundColor: STATUS_COLORS[k].border,
    }));

    const barGlow = {
      id: 'barGlow',
      beforeDatasetsDraw(chart) {
        chart.ctx.save();
        chart.ctx.shadowColor = 'rgba(6,182,212,0.35)';
        chart.ctx.shadowBlur = 8;
      },
      afterDatasetsDraw(chart) { chart.ctx.restore(); }
    };

    _bar = new Chart(ctx, {
      type: 'bar',
      data: { labels: persons.map(p => p.name), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        animation: { duration: 700 },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: textColor(), font: { size: 10, family: '"JetBrains Mono", Menlo, monospace' }, boxWidth: 10, padding: 6 }
          },
          tooltip: {
            backgroundColor: 'rgba(15,21,36,0.92)',
            borderColor: 'rgba(6,182,212,0.5)',
            borderWidth: 1,
            titleColor: '#7FF3FF',
            bodyColor: '#E8EDFA',
          }
        },
        scales: {
          x: {
            stacked: true,
            grid: { color: gridColor() },
            ticks: { color: textColor(), font: { size: 11, family: '"JetBrains Mono", Menlo, monospace' }, precision: 0 }
          },
          y: {
            stacked: true,
            grid: { display: false },
            ticks: { color: textColor(), font: { size: 11, family: '"JetBrains Mono", Menlo, monospace' } }
          }
        }
      },
      plugins: [barGlow],
    });
  }

  function initTimeline(canvasId, tasks) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (_timeline) _timeline.destroy();

    // Count tasks per day in next 30 days
    const today = new Date(); today.setHours(0,0,0,0);
    const days = 30;
    const counts = new Array(days).fill(0);
    const labels = [];
    for (let i = 0; i < days; i++) {
      const d = new Date(today); d.setDate(today.getDate() + i);
      labels.push(i === 0 ? '今天' : `${d.getMonth()+1}/${d.getDate()}`);
    }

    for (const t of tasks) {
      if (!t.ddl) continue;
      const ddl = new Date(t.ddl); ddl.setHours(0,0,0,0);
      const diff = Math.round((ddl - today) / 86400000);
      if (diff >= 0 && diff < days) counts[diff]++;
    }

    if (counts.every(v => v === 0)) return;

    const bgColors = counts.map((_,i) =>
      i === 0 ? '#FF2E63' : i < 3 ? '#FF8A00' : i < 7 ? '#FBBF24' : '#34D399'
    );

    const todayPulse = {
      id: 'todayPulse',
      afterDatasetDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        const bar = meta.data[0];
        if (!bar) return;
        const ctx2 = chart.ctx;
        const t = (performance.now() % 1600) / 1600;
        const alpha = 0.35 + 0.45 * Math.abs(Math.sin(t * Math.PI));
        ctx2.save();
        ctx2.shadowColor = `rgba(255,46,99,${alpha})`;
        ctx2.shadowBlur = 22;
        ctx2.fillStyle = '#FF2E63';
        ctx2.beginPath();
        ctx2.arc(bar.x, bar.y - 6, 3.5, 0, Math.PI * 2);
        ctx2.fill();
        ctx2.restore();
      }
    };

    const tlGlow = {
      id: 'tlGlow',
      beforeDatasetsDraw(c) { c.ctx.save(); c.ctx.shadowColor = 'rgba(208,31,246,0.25)'; c.ctx.shadowBlur = 10; },
      afterDatasetsDraw(c)  { c.ctx.restore(); }
    };

    _timeline = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: counts,
          backgroundColor: bgColors,
          borderRadius: 4,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15,21,36,0.92)',
            borderColor: 'rgba(208,31,246,0.5)',
            borderWidth: 1,
            titleColor: '#EE87FF',
            bodyColor: '#E8EDFA',
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: textColor(), font: { size: 10, family: '"JetBrains Mono", Menlo, monospace' },
              maxRotation: 0,
              maxTicksLimit: 10,
            }
          },
          y: {
            grid: { color: gridColor() },
            ticks: { color: textColor(), font: { size: 11, family: '"JetBrains Mono", Menlo, monospace' }, precision: 0 }
          }
        }
      },
      plugins: [tlGlow, todayPulse],
    });

    // Drive pulse redraw at ~20fps (cheap)
    if (_timeline._pulseInt) clearInterval(_timeline._pulseInt);
    _timeline._pulseInt = setInterval(() => {
      if (_timeline) _timeline.draw();
    }, 50);
  }

  return { initDonut, initBar, initTimeline, destroyAll };
})();

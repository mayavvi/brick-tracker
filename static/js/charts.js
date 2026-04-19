/**
 * Chart.js chart management for the tracker dashboard.
 * Provides donut (status), bar (person workload), and DDL timeline charts.
 */

const TrackerCharts = (() => {
  let _donut = null;
  let _bar = null;
  let _timeline = null;

  const STATUS_COLORS = {
    in_progress:        { bg: '#fbbf24', border: '#f59e0b' },
    completed_ready_qc: { bg: '#60a5fa', border: '#3b82f6' },
    has_issues:         { bg: '#f87171', border: '#ef4444' },
    pending:            { bg: '#9ca3af', border: '#6b7280' },
    closed:             { bg: '#34d399', border: '#10b981' },
  };

  const STATUS_LABELS = {
    in_progress: '搬砖中',
    completed_ready_qc: '搬完了',
    has_issues: '有坑',
    pending: '先放着',
    closed: '收工',
  };

  function isDark() {
    return document.documentElement.classList.contains('dark');
  }

  function textColor() {
    return isDark() ? '#d0b888' : '#6b4a20';
  }

  function gridColor() {
    return isDark() ? 'rgba(80,50,20,0.4)' : 'rgba(200,150,80,0.2)';
  }

  function destroyAll() {
    if (_donut)    { _donut.destroy();    _donut = null; }
    if (_bar)      { _bar.destroy();      _bar = null; }
    if (_timeline) { _timeline.destroy(); _timeline = null; }
  }

  function initDonut(canvasId, summary) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (_donut) _donut.destroy();

    const keys   = Object.keys(STATUS_COLORS);
    const values = keys.map(k => summary[k] || 0);
    const total  = values.reduce((a, b) => a + b, 0);
    if (total === 0) { ctx.getContext('2d').clearRect(0, 0, ctx.width, ctx.height); return; }

    _donut = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: keys.map(k => STATUS_LABELS[k]),
        datasets: [{
          data: values,
          backgroundColor: keys.map(k => STATUS_COLORS[k].bg),
          borderColor:     keys.map(k => STATUS_COLORS[k].border),
          borderWidth: 2,
          hoverOffset: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: textColor(),
              font: { size: 11 },
              boxWidth: 10,
              padding: 8,
            }
          },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                const pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
                return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
              }
            }
          }
        }
      }
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
      borderRadius: 3,
    }));

    _bar = new Chart(ctx, {
      type: 'bar',
      data: { labels: persons.map(p => p.name), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: textColor(), font: { size: 10 }, boxWidth: 10, padding: 6 }
          }
        },
        scales: {
          x: {
            stacked: true,
            grid: { color: gridColor() },
            ticks: { color: textColor(), font: { size: 11 }, precision: 0 }
          },
          y: {
            stacked: true,
            grid: { display: false },
            ticks: { color: textColor(), font: { size: 11 } }
          }
        }
      }
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
      i === 0 ? '#ef4444' : i < 3 ? '#f97316' : i < 7 ? '#fbbf24' : '#34d399'
    );

    _timeline = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: counts,
          backgroundColor: bgColors,
          borderRadius: 3,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: textColor(), font: { size: 10 },
              maxRotation: 0,
              maxTicksLimit: 10,
            }
          },
          y: {
            grid: { color: gridColor() },
            ticks: { color: textColor(), font: { size: 11 }, precision: 0 }
          }
        }
      }
    });
  }

  return { initDonut, initBar, initTimeline, destroyAll };
})();

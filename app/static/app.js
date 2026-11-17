'use strict';

let STATE = null;
const charts = {};
let map = null;

// Basispad van de app: leeg in de gewone uitrol, "/test" in de testomgeving.
// De <html data-app-base=...> komt uit de template (request.script_name).
const API = (document.documentElement.dataset.appBase || '');

const $ = (s) => document.querySelector(s);

// Zowel het attribuut als de inline style, zodat het werkt ongeacht of een
// author-CSS-regel de UA-regel [hidden]{display:none} overruled.
function show(el, on, mode) {
  if (!el) return;
  el.hidden = !on;
  el.style.display = on ? (mode || '') : 'none';
}
const fmtMin = (m) => {
  if (m == null) return '–';
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return h ? `${h}u${String(r).padStart(2, '0')}` : `${r} min`;
};
const fmtHms = (m) => {
  if (m == null) return '–';
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return `${h}:${String(r).padStart(2, '0')}`;
};
const DOW = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'];
const dayLabel = (iso) => {
  const d = new Date(iso + 'T12:00:00');
  return `${DOW[(d.getDay() + 6) % 7]} ${d.getDate()}/${d.getMonth() + 1}`;
};

if (window.Chart) {
  Chart.defaults.color = '#8e9bb0';
  Chart.defaults.borderColor = '#1d2432';
  Chart.defaults.font.family = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
  Chart.defaults.plugins.legend.labels.padding = 14;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  // Tooltips in dezelfde taal als de kaarten: donker paneel, zachte rand.
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: '#1b2130f2', borderColor: '#2a3346', borderWidth: 1,
    titleColor: '#e8edf6', bodyColor: '#b8c3d4', footerColor: '#8e9bb0',
    padding: 11, cornerRadius: 9, boxPadding: 5, displayColors: true,
  });
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.point.hoverRadius = 5;
}

async function load(refresh) {
  show($('#loading'), true, 'grid');
  try {
    const r = await fetch(API + '/api/state' + (refresh ? '?refresh=1' : ''));
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    STATE = j;
    show($('#main'), true, 'flex');
    render();
    loadRoutes();
    loadDiag();
  } catch (e) {
    console.error(e);
    $('#loading').innerHTML = 'Kon data niet laden: ' + e.message +
      '<br><br><button class="btn" onclick="location.reload()">Opnieuw</button>';
    return;
  }
  show($('#loading'), false);
}

const SECTIONS = [
  ['header', renderHeader], ['countdown', renderCountdown], ['tiles', renderTiles],
  ['bijstelling', renderAdapt], ['deze week', renderThisWeek], ['volume', renderVolume], ['duurloop', renderLong],
  ['vorm', renderForm], ['acwr', renderAcwr], ['zones', renderZones], ['herstel', renderRecovery],
  ['verwachting', renderProjection], ['plan', renderPlanTable],
];

function render() {
  const broken = [];
  SECTIONS.forEach(([name, fn]) => {
    try { fn(); } catch (e) {
      console.error('render ' + name + ' faalde', e);
      broken.push(name + ': ' + e.message);
    }
  });
  const warn = $('#renderWarn');
  if (broken.length) {
    show(warn, true, 'block');
    warn.className = 'msg err';
    warn.innerHTML = 'Deze onderdelen konden niet getekend worden:<br>' + broken.join('<br>');
  } else {
    show(warn, false);
  }
}

function renderHeader() {
  const g = STATE.goal;
  $('#goalName').textContent = g.goal_name;
  const d = new Date(g.race_date + 'T12:00:00');
  $('#goalSub').textContent =
    `${g.distance_km} km · ${d.toLocaleDateString('nl-NL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}` +
    ` · ${g.days_per_week}x per week · ${g.priority === 'health' ? 'gezond finishen' : 'streeftijd'}`;
}

function renderCountdown() {
  const p = STATE.plan;
  $('#cdDays').textContent = STATE.days_to_race;
  const cur = currentWeek();
  const done = cur ? cur.index - 1 : 0;
  const pct = Math.max(0, Math.min(100, (done / p.weeks_total) * 100));
  $('#cdFill').style.width = pct + '%';
  $('#cdWeek').textContent = cur
    ? `week ${cur.index} van ${p.weeks_total}`
    : `plan start ${p.weeks[0].start}`;
  $('#cdPhase').textContent = cur ? (cur.deload ? cur.phase + ' · herstelweek' : cur.phase) : '–';
}

function currentWeek() {
  const t = STATE.today;
  return STATE.plan.weeks.find((w) => w.start <= t && t <= w.end) || null;
}

function tile(k, v, n, cls) {
  return `<div class="tile ${cls || ''}"><div class="k">${k}</div>
    <div class="v">${v}</div><div class="n">${n || ''}</div></div>`;
}

function recKort(rec) {
  /* Eerste regel van het readiness-advies, leesbaar gemaakt voor de tegel:
     het voorvoegsel staat al als kop van de tegel, de verwijzing naar de
     interne beslisregel (bijv. "(decision_rule pairs)") is jargon, en een
     harde afkapping midden in een woord leest slecht. */
  let s = String(rec || '').replace(/^(GO|MODIFY|REST):\s*/, '');
  s = s.replace(/\s*\((?:decision_rule|decision)[^)]*\)\.?$/, '').trim();
  s = s.replace(/^(\d+) red \((\w+)\) without a red pair$/i,
    '$1 rood signaal ($2), zonder tweede rood signaal erbij');
  if (s.length > 64) s = s.slice(0, 64).replace(/\s+\S*$/, '') + '…';
  return s;
}

function renderTiles() {
  const m = STATE.metrics, b = STATE.baseline, p = STATE.plan;
  const ts = m.training_status.value || {};
  const ld = (m.load.value && m.load.value.data && m.load.value.data.latest) || {};
  const rp = m.race_predictions.value || {};
  const rd = (m.readiness.value && m.readiness.value.data) || {};
  const out = [];

  out.push(tile('Langste run', b.longest_km ? b.longest_km.toFixed(1) + ' km' : '–',
    b.longest_min ? fmtMin(b.longest_min) : ''));
  out.push(tile('Nodig op racedag', p.config.distance_km + ' km',
    b.longest_km ? `nog ${(p.config.distance_km - b.longest_km).toFixed(1)} km te bouwen` : ''));
  out.push(tile('Runs laatste 90d', b.runs_90d != null ? b.runs_90d : '–',
    b.km_90d != null ? b.km_90d + ' km totaal' : ''));
  out.push(tile('VO2max', ts.vo2_max_precise || ts.vo2_max || '–',
    ts.training_status_feedback ? String(ts.training_status_feedback).toLowerCase().replace(/_/g, ' ') : ''));
  if (ld.ctl != null) {
    const tsb = ld.tsb;
    out.push(tile('Vorm (TSB)', (tsb > 0 ? '+' : '') + Math.round(tsb),
      `fitheid ${Math.round(ld.ctl)} · moeheid ${Math.round(ld.atl)}`,
      tsb < -20 ? 'bad' : tsb < -10 ? 'warn' : 'good'));
    out.push(tile('ACWR', ld.acwr != null ? ld.acwr.toFixed(2) : '–',
      ld.acwr == null ? '' : (ld.acwr > 1.3 ? 'te snel opgebouwd' : ld.acwr < 0.8 ? 'weinig prikkel' : 'veilige zone'),
      ld.acwr == null ? '' : (ld.acwr > 1.3 ? 'bad' : ld.acwr < 0.8 ? 'warn' : 'good')));
  }
  if (rd.decision) {
    const dm = { GO: 'good', MODIFY: 'warn', REST: 'bad' };
    const rec = Array.isArray(rd.recommendation) ? rd.recommendation[0] : rd.recommendation;
    out.push(tile('Vandaag', rd.decision, recKort(rec), dm[rd.decision]));
  }
  const hm = rp.predictions && rp.predictions.half_marathon;
  const e = p.estimate;
  if (e.target_min) {
    out.push(tile('Doel', fmtHms(e.target_min),
      e.target_pace_min_per_km.toFixed(2) + ' min/km',
      e.target_within_band ? 'good' : 'warn'));
  }
  if (e.pr) out.push(tile('Je PR', fmtHms(e.pr.minutes), e.pr.date));
  out.push(tile('Verwacht', fmtHms(e.race_minutes_after),
    'band ' + fmtHms(e.race_minutes_best) + '-' + fmtHms(e.race_minutes_worst)));
  out.push(tile('Piek duurloop', fmtMin(e.peak_long_min), 'in week ' + peakWeek()));
  $('#tiles').innerHTML = out.join('');
}

function peakWeek() {
  let best = STATE.plan.weeks[0];
  STATE.plan.weeks.forEach((w) => { if (w.long_min > best.long_min) best = w; });
  return best.index;
}


function renderAdapt() {
  const weeks = STATE.plan.weeks;
  const today = STATE.today;
  const upcoming = weeks.find((w) => w.start > today);
  const current = weeks.find((w) => w.start <= today && today <= w.end);
  const ad = (upcoming && upcoming.adapted) || (current && current.adapted) || null;
  const target = (upcoming && upcoming.adapted) ? upcoming : current;

  const when = STATE.last_adaptation_target || STATE.last_adaptation_week;
  const hb = STATE.scheduler;
  const DAGEN = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag'];
  let sched = 'planner niet actief';
  if (hb) {
    const age = Math.round((Date.now() / 1000 - hb.at) / 60);
    sched = `planner actief · ${DAGEN[hb.weekday]} vanaf ${String(hb.after_hour).padStart(2, '0')}:00` +
            ` · laatste controle ${age} min geleden`;
  }
  $('#adaptWhen').innerHTML = (when
    ? `laatst beoordeeld voor de week van ${when}`
    : 'nog niet beoordeeld') + `<br><span style="color:var(--ink3)">${sched}</span>`;

  if (!ad) {
    $('#adaptBody').innerHTML =
      `<p class="muted">Nog geen bijstelling. Elke maandagochtend weegt het dashboard je
       trainings- en herstelgegevens en past daarop de eerstvolgende week aan:
       belastingverhouding (ACWR), vorm, Garmin readiness, HRV, rusthartslag, slaap,
       en hoeveel van het plan je echt hebt gedaan.</p>`;
    return;
  }

  const pct = Math.round((ad.scale - 1) * 100);
  const cls = ad.scale < 0.98 ? 'bad' : ad.scale > 1.02 ? 'good' : '';
  $('#adaptBody').innerHTML = `
    <div class="adaptHead">
      <span class="adaptBadge ${cls}">${ad.severity}${pct ? ` ${pct > 0 ? '+' : ''}${pct}%` : ''}</span>
      <span class="muted">week van ${target.start}${ad.drop_quality
        ? ' · kwaliteitssessie geschrapt' : ''}</span>
    </div>
    <ul class="adaptList">${(ad.reasons || []).map((r) => `<li>${r}</li>`).join('')}</ul>`;
}

function renderThisWeek() {
  const wk = currentWeek() || STATE.plan.weeks[0];
  const ups = STATE.uploads || {};
  $('#weekSummary').textContent =
    `week ${wk.index} · ${wk.phase}${wk.deload ? ' (herstel)' : ''} · ${fmtMin(wk.planned_min)} gepland` + (wk.run_walk ? ` · run:walk ${wk.run_walk}` : '');
  $('#thisWeek').innerHTML = wk.sessions.map((s) => {
    const key = `${s.date}|${s.kind}`;
    const up = ups[key];
    const btn = s.uploadable
      ? (up
        ? `<span class="okmark">✓ staat in Garmin</span>`
        : `<button class="btn small up" data-date="${s.date}" data-kind="${s.kind}">Naar Garmin</button>`)
      : '';
    const ex = s.exercises
      ? `<table class="exTable">${s.exercises.map((x) =>
          `<tr><td class="exSets">${x.sets}&times;${x.reps}</td><td>${x.name}` +
          `${x.hint ? `<span class="exHint">${x.hint}</span>` : ''}</td></tr>`).join('')}</table>`
      : '';
    return `<div class="sess ${up ? 'done' : ''}">
      <div class="day">${dayLabel(s.date)}<small>${s.date}</small></div>
      <div>
        <div class="lbl">${s.label}<span class="tag ${s.kind}">${s.kind}</span></div>
        <div class="det">${s.exercises ? (s.focus || '') : s.detail}</div>
        ${ex}
        ${s.note ? `<div class="note">${s.note}</div>` : ''}
      </div>
      <div><div class="mins">${fmtMin(s.minutes)}</div>${btn}</div>
    </div>`;
  }).join('');
  $('#btnUploadWeek').dataset.week = wk.index;
}

function mkChart(id, cfg) {
  const el = $('#' + id);
  if (!el) return;                       // slot is al vervangen door een melding
  if (typeof Chart === 'undefined') {
    noData(id, 'Grafiekbibliotheek kon niet geladen worden (geen internet op de server?).');
    return;
  }
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  charts[id] = new Chart(el, cfg);
}

function renderVolume() {
  const weeks = STATE.plan.weeks, act = STATE.actuals || {};
  mkChart('chVolume', {
    type: 'bar',
    data: {
      labels: weeks.map((w) => 'W' + w.index),
      datasets: [
        {
          label: 'Gepland', data: weeks.map((w) => w.planned_min),
          backgroundColor: weeks.map((w) => w.deload ? '#2c3545' : '#2f5f8f'),
          borderRadius: 3, order: 2,
        },
        {
          label: 'Werkelijk gelopen', type: 'line',
          data: weeks.map((w) => (act[w.start] ? act[w.start].minutes : null)),
          borderColor: '#3ddc97', backgroundColor: '#3ddc97',
          pointRadius: 3, tension: .3, spanGaps: false, order: 1,
        },
      ],
    },
    options: {
      scales: {
        y: { title: { display: true, text: 'minuten' }, beginAtZero: true },
        x: { grid: { display: false }, ticks: { maxRotation: 0 } },
      },
      plugins: {
        tooltip: {
          callbacks: {
            afterTitle: (it) => {
              const w = weeks[it[0].dataIndex];
              return w.phase + (w.deload ? ' · herstelweek' : '') + (w.run_walk ? ' · run:walk ' + w.run_walk : '');
            },
          },
        },
      },
    },
  });
}

function renderLong() {
  const weeks = STATE.plan.weeks;
  mkChart('chLong', {
    type: 'line',
    data: {
      labels: weeks.map((w) => 'W' + w.index),
      datasets: [{
        label: 'Duurloop (min)', data: weeks.map((w) => w.long_min || null),
        borderColor: '#b48cff', backgroundColor: '#b48cff22',
        fill: true, tension: .3, pointRadius: 2, spanGaps: true,
      }, {
        label: `Verwachte racetijd na het plan (${fmtHms(STATE.plan.estimate.race_minutes_after)})`,
        data: weeks.map(() => STATE.plan.estimate.race_minutes_after),
        borderColor: '#ff6b6b', borderDash: [5, 4], pointRadius: 0, fill: false,
      }, {
        label: STATE.plan.estimate.target_min
          ? `Je doel (${fmtHms(STATE.plan.estimate.target_min)})`
          : `Als je nu zou starten (${fmtHms(STATE.plan.estimate.race_minutes_now)})`,
        data: weeks.map(() => STATE.plan.estimate.target_min || STATE.plan.estimate.race_minutes_now),
        borderColor: '#3ddc97', borderDash: [2, 4], pointRadius: 0, fill: false,
      }],
    },
    options: {
      scales: { y: { title: { display: true, text: 'minuten' }, beginAtZero: true }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (c) => c.datasetIndex === 0 ? 'Duurloop ' + fmtMin(c.parsed.y) : c.dataset.label } } },
    },
  });
}

function renderForm() {
  const ld = STATE.metrics.load.value;
  const series = (ld && ld.data && ld.data.series) || [];
  if (!series.length) { noData('chForm', 'Nog te weinig data voor een vormcurve.'); return; }
  mkChart('chForm', {
    type: 'line',
    data: {
      labels: series.map((p) => p.date),
      datasets: [
        { label: 'Fitheid (CTL)', data: series.map((p) => p.ctl), borderColor: '#4ea8ff', pointRadius: 0, tension: .3 },
        { label: 'Moeheid (ATL)', data: series.map((p) => p.atl), borderColor: '#ffb454', pointRadius: 0, tension: .3 },
        { label: 'Vorm (TSB)', data: series.map((p) => p.tsb), borderColor: '#3ddc97', pointRadius: 0, tension: .3, fill: { target: { value: 0 }, above: '#3ddc9718', below: '#ff6b6b18' } },
      ],
    },
    options: { scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } } } },
  });
}

function renderAcwr() {
  const weeks = STATE.plan.weeks;
  const lm = STATE.plan.load_model || {};
  const warn = lm.acwr_warn || 1.3, high = 1.5, low = lm.acwr_low || 0.8;
  const ld = STATE.metrics.load.value;
  const actualNow = ld && ld.data && ld.data.latest ? ld.data.latest.acwr : null;

  // Weken in het opwarm-regime apart: daar is de ratio wiskundig onbruikbaar
  // omdat de chronische belasting bijna nul is.
  const planned = weeks.map((w) => (w.acwr_note === 'normaal' ? w.acwr : null));
  const warming = weeks.map((w) => (w.acwr_note === 'opwarmen' ? Math.min(w.acwr, 2.5) : null));

  mkChart('chAcwr', {
    type: 'line',
    data: {
      labels: weeks.map((w) => 'W' + w.index),
      datasets: [
        { label: 'Gepland', data: planned, borderColor: '#4ea8ff',
          backgroundColor: '#4ea8ff22', pointRadius: 2, tension: .25, spanGaps: false, fill: true },
        { label: 'Opwarmfase (ratio zegt hier niets)', data: warming,
          borderColor: '#6b7483', borderDash: [3, 3], pointRadius: 2, tension: .25, spanGaps: false },
        { label: `Waarschuwing (${warn})`, data: weeks.map(() => warn),
          borderColor: '#ffb454', borderDash: [5, 4], pointRadius: 0 },
        { label: `Hoog risico (${high})`, data: weeks.map(() => high),
          borderColor: '#ff6b6b', borderDash: [5, 4], pointRadius: 0 },
        { label: `Te weinig prikkel (${low})`, data: weeks.map(() => low),
          borderColor: '#3ddc9755', borderDash: [2, 4], pointRadius: 0 },
      ],
    },
    options: {
      scales: { y: { beginAtZero: true, suggestedMax: 1.8, title: { display: true, text: 'ratio' } },
                x: { grid: { display: false } } },
      plugins: {
        tooltip: { callbacks: { afterBody: (it) => {
          const w = weeks[it[0].dataIndex];
          const bits = [`${w.planned_min} loopmin, belasting ${w.load}`];
          if (w.chronic) bits.push(`chronisch ${w.chronic}`);
          if (w.capped) bits.push(`afgeremd (${w.capped.reason})`);
          if (actualNow != null && w.start <= STATE.today && STATE.today <= w.end) {
            bits.push(`werkelijk nu: ${actualNow}`);
          }
          return bits.join(' · ');
        } } },
      },
    },
  });
}

function renderZones() {
  const ld = STATE.metrics.load.value;
  const it = (ld && ld.data && ld.data.intensity) || null;
  if (!it) { noData('chZones', 'Nog geen zoneverdeling beschikbaar.'); return; }
  const target = it.z1_min_pct || 75;
  mkChart('chZones', {
    type: 'bar',
    data: {
      labels: ['Onder LT1 (aeroob)', 'LT1–LTHR', 'Boven LTHR'],
      datasets: [{
        label: '% van looptijd',
        data: [it.z1_pct, it.z2_pct, it.z3_pct],
        backgroundColor: ['#3ddc97', '#ffb454', '#ff6b6b'], borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      scales: { x: { beginAtZero: true, max: 100, title: { display: true, text: `% · doel voor aeroob is ${target}%` } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { afterLabel: (c) => c.dataIndex === 0 ? `doel: ${target}% of meer` : '' } },
      },
    },
  });
}

function renderRecovery() {
  const h = STATE.metrics.health.value;
  const rows = (h && h.data && h.data.rows) || [];
  if (!rows.length) { noData('chRecovery', 'Nog geen herstelreeksen beschikbaar.'); return; }
  const labels = rows.map((r) => r.date);
  mkChart('chRecovery', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Rusthartslag', data: rows.map((r) => r.resting_hr_bpm ?? null),
          borderColor: '#ff6b6b', pointRadius: 0, tension: .3, spanGaps: true,
          yAxisID: 'y', borderWidth: 2,
        },
        {
          label: 'HRV', data: rows.map((r) => r.hrv_ms ?? null),
          borderColor: '#4ea8ff', pointRadius: 0, tension: .3, spanGaps: true,
          yAxisID: 'y1', borderWidth: 2,
        },
        {
          label: 'HRV-basislijn', data: rows.map((r) => r.hrv_baseline_high_ms ?? null),
          borderColor: '#4ea8ff44', pointRadius: 0, borderWidth: 1, fill: '+1',
          backgroundColor: '#4ea8ff12', yAxisID: 'y1', spanGaps: true,
        },
        {
          label: '', data: rows.map((r) => r.hrv_baseline_low_ms ?? null),
          borderColor: '#4ea8ff44', pointRadius: 0, borderWidth: 1, fill: false,
          yAxisID: 'y1', spanGaps: true,
        },
      ],
    },
    options: {
      scales: {
        y: { position: 'left', title: { display: true, text: 'bpm' } },
        y1: { position: 'right', title: { display: true, text: 'HRV (ms)' }, grid: { drawOnChartArea: false } },
        x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { filter: (i) => i.text !== '' } },
        tooltip: { callbacks: { afterBody: (it) => {
          const r = rows[it[0].dataIndex];
          const bits = [];
          if (r.sleep_h != null) bits.push('slaap ' + r.sleep_h + ' u' + (r.sleep_score != null ? ' (score ' + r.sleep_score + ')' : ''));
          if (r.hrv_status) bits.push('HRV ' + r.hrv_status);
          return bits.join(' · ');
        } } },
      },
    },
  });
}

function noData(id, msg) {
  const c = $('#' + id);
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  if (!c) return;
  const wrap = c.parentElement;
  wrap.innerHTML = `<p class="muted" style="padding:28px 0;text-align:center">${msg}</p>`
    + `<canvas id="${id}" hidden></canvas>`;   // slot blijft bestaan voor een volgende render
}

function renderProjection() {
  const p = STATE.plan, m = STATE.metrics, e = p.estimate;
  const rp = m.race_predictions.value || {};
  const hm = rp.predictions && (rp.predictions.half_marathon || rp.predictions['21.1K']);
  const rows = [];

  if (e.target_min) {
    const haalbaar = e.target_within_band;
    const gap = e.target_gap_min;
    rows.push(['Je doel', fmtHms(e.target_min),
      `${(e.target_pace_min_per_km).toFixed(2)} min/km volgehouden`]);
    rows.push(['Verwacht na het plan', fmtHms(e.race_minutes_after),
      `bandbreedte ${fmtHms(e.race_minutes_best)} tot ${fmtHms(e.race_minutes_worst)}` +
      (haalbaar
        ? ` — je doel valt binnen die band${gap > 0 ? `, ${Math.round(gap)} min boven het midden` : ''}`
        : ` — je doel ligt ${Math.round(gap)} min onder de beste uitkomst`)]);
  } else {
    rows.push(['Verwacht na het plan', fmtHms(e.race_minutes_after),
      `bandbreedte ${fmtHms(e.race_minutes_best)} tot ${fmtHms(e.race_minutes_worst)}`]);
  }

  if (e.pr) {
    rows.push(['Je beste tot nu toe', fmtHms(e.pr.minutes),
      `${e.pr.date} · ${e.pr.km} km · ${e.pr.pace_min_per_km.toFixed(2)} min/km` +
      (e.pr.avg_hr ? ` · gem. HR ${Math.round(e.pr.avg_hr)}` : '')]);
  }
  rows.push(['Als je nu zou starten', fmtHms(e.race_minutes_now),
    'uit je huidige vorm — je bent nog aan het terugbouwen']);
  if (hm) rows.push(['Garmin voorspelt', hm.time, 'rekent alleen met je recente runs']);

  $('#projection').innerHTML = rows.map((r) =>
    `<div class="projRow"><div><div class="pl">${r[0]}</div>
      <div class="projNote">${r[2]}</div></div><div class="pv">${r[1]}</div></div>`).join('')
    + `<p class="projNote">${e.note || ''}</p>`;
}

const KIND_LABEL = {
  easy: 'rustig', long: 'duurloop', tempo: 'tempo', intervals: 'interval',
  threshold: 'drempel', hills: 'heuvels', strides: 'versnellingen',
  strength: 'kracht', race: 'race',
};

function sessionRow(s, ups) {
  const key = `${s.date}|${s.kind}`;
  const up = ups[key];
  const hr = s.hr ? `${s.hr[0]}&ndash;${s.hr[1]} bpm` : '';
  const btn = s.uploadable
    ? (up ? '<span class="okmark">&check; in Garmin</span>'
          : `<button class="btn small up" data-date="${s.date}" data-kind="${s.kind}">Naar Garmin</button>`)
    : '';
  const ex = s.exercises
    ? `<div class="exMini">${s.exercises.map((x) => `${x.sets}&times;${x.reps} ${x.name}`).join(' &middot; ')}</div>`
    : '';
  return `<div class="planSess">
    <div class="psDay">${dayLabel(s.date)}</div>
    <div class="psBody">
      <div class="psTop"><span class="tag ${s.kind}">${KIND_LABEL[s.kind] || s.kind}</span>
        <b>${s.label}</b>
        <span class="muted">${fmtMin(s.minutes)}${hr ? ' &middot; ' + hr : ''}</span></div>
      <div class="psDetail">${s.detail || ''}</div>
      ${ex}
      ${s.note ? `<div class="psNote">${s.note}</div>` : ''}
    </div>
    <div class="psAct">${btn}</div>
  </div>`;
}

function renderPlanTable() {
  const weeks = STATE.plan.weeks, act = STATE.actuals || {}, t = STATE.today;
  const ups = STATE.uploads || {};
  const lm = STATE.plan.load_model || {};
  $('#planMeta').textContent =
    `${STATE.plan.weeks_total} weken · basis ${STATE.plan.phases.basis}, opbouw ${STATE.plan.phases.opbouw}, ` +
    `piek ${STATE.plan.phases.piek}, taper ${STATE.plan.phases.taper} · ACWR-plafond ${lm.acwr_cap_used || '–'}`;

  $('#planTable tbody').innerHTML = weeks.map((w) => {
    const a = act[w.start];
    const now = w.start <= t && t <= w.end;
    const past = w.end < t;

    const kinds = w.sessions.map((s) =>
      `<span class="tag ${s.kind}" title="${s.label}: ${fmtMin(s.minutes)}">${KIND_LABEL[s.kind] || s.kind}</span>`).join(' ');

    const flags = [];
    if (w.deload) flags.push('<span class="flag">herstelweek</span>');
    if (w.capped) flags.push(`<span class="flag warn" title="automatisch afgeremd op opbouwsnelheid">afgeremd: ${w.capped.reason}</span>`);
    if (w.adapted) flags.push(`<span class="flag bad" title="${(w.adapted.reasons || []).join('; ')}">bijgesteld ${w.adapted.severity}</span>`);
    if (!flags.length) flags.push('<span class="muted">&ndash;</span>');

    const acwrCls = w.acwr == null ? '' :
      (w.acwr_note === 'opwarmen' ? 'muted' : w.acwr > 1.3 ? 'bad' : w.acwr < 0.8 ? 'warn' : 'good');
    const acwr = w.acwr == null ? '&ndash;'
      : `<span class="${acwrCls}" title="belasting ${w.load}${w.chronic ? ', chronisch ' + w.chronic : ''}${w.acwr_note === 'opwarmen' ? ' — opwarmfase, ratio zegt hier weinig' : ''}">${w.acwr.toFixed(2)}</span>`;

    const done = a
      ? `${fmtMin(a.minutes)}<small class="muted"> / ${a.sessions}x</small>`
      : (past ? '<span class="bad">0</span>' : '&ndash;');

    const btn = w.sessions.some((s) => s.uploadable)
      ? `<button class="btn small upweek" data-week="${w.index}">Naar Garmin</button>` : '';

    return `<tr class="wkRow ${now ? 'now' : ''} ${w.deload ? 'deload' : ''}" data-week="${w.index}">
        <td class="expander"><button class="exp" data-week="${w.index}" aria-label="uitklappen">&#9656;</button></td>
        <td>${w.index}</td><td>${w.start}</td>
        <td>${w.phase}</td>
        <td class="num">${w.long_min ? fmtMin(w.long_min) : '&ndash;'}</td>
        <td class="num">${fmtMin(w.planned_min)}</td>
        <td class="num">${done}</td>
        <td class="num">${acwr}</td>
        <td class="kindCell">${kinds}</td>
        <td class="flagCell">${flags.join(' ')}</td>
        <td>${btn}</td></tr>
      <tr class="detailRow" data-week="${w.index}" hidden><td></td><td colspan="10">
        ${w.sessions.map((s) => sessionRow(s, ups)).join('')}
        <p class="muted" style="margin-top:8px">Loopvolume telt krachttraining niet mee.</p>
      </td></tr>`;
  }).join('');
}

function toggleWeek(n, force) {
  const row = document.querySelector(`tr.detailRow[data-week="${n}"]`);
  const btn = document.querySelector(`button.exp[data-week="${n}"]`);
  if (!row) return;
  const open = force === undefined ? row.hidden : force;
  show(row, open, 'table-row');
  if (btn) btn.innerHTML = open ? '&#9662;' : '&#9656;';
}

document.addEventListener('click', (e) => {
  const exp = e.target.closest && e.target.closest('button.exp');
  if (exp) { toggleWeek(exp.dataset.week); return; }
  if (e.target.id === 'btnExpandAll') {
    const anyClosed = [...document.querySelectorAll('tr.detailRow')].some((r) => r.hidden);
    STATE.plan.weeks.forEach((w) => toggleWeek(w.index, anyClosed));
    e.target.textContent = anyClosed ? 'Alles inklappen' : 'Alles uitklappen';
  }
});

const ROUTE_COLORS = ['#4ea8ff', '#3ddc97', '#b48cff', '#ffb454', '#ff6b6b',
                      '#8fa3bf', '#f58fd0', '#6fe3d2'];
let ROUTES = [];
let layerControl = null;

function routePrefs() {
  try { return JSON.parse(localStorage.getItem('routesOff') || '[]'); } catch (e) { return []; }
}
function saveRoutePrefs(off) {
  try { localStorage.setItem('routesOff', JSON.stringify(off)); } catch (e) { /* prive-modus */ }
}
function isOn(id) { return !routePrefs().includes(String(id)); }

function setRoute(id, on, syncControl) {
  const rt = ROUTES.find((r) => String(r.id) === String(id));
  if (!rt) return;
  const off = routePrefs().filter((x) => x !== String(id));
  if (!on) off.push(String(id));
  saveRoutePrefs(off);

  if (on && !map.hasLayer(rt.layer)) rt.layer.addTo(map);
  if (!on && map.hasLayer(rt.layer)) map.removeLayer(rt.layer);

  const chip = document.querySelector('.routeChip[data-id="' + id + '"]');
  if (chip) {
    chip.classList.toggle('off', !on);
    const cb = chip.querySelector('input');
    if (cb) cb.checked = on;
  }
  if (syncControl) syncLayerControl();
  updateRouteCount();
}

function syncLayerControl() {
  // De ingebouwde Leaflet-regelaar heeft geen setter; opnieuw opbouwen is het
  // eenvoudigst en blijft zo gegarandeerd in sync met de chips.
  if (layerControl) { map.removeControl(layerControl); layerControl = null; }
  const overlays = {};
  ROUTES.forEach((rt, i) => {
    const dot = '<span style="display:inline-block;width:10px;height:3px;border-radius:2px;'
      + 'background:' + ROUTE_COLORS[i % ROUTE_COLORS.length] + ';vertical-align:middle;margin-right:6px"></span>';
    overlays[dot + rt.date + ' \u00b7 ' + rt.km + ' km'] = rt.layer;
  });
  layerControl = L.control.layers(null, overlays, { collapsed: false, position: 'topright' });
  layerControl.addTo(map);
}

function visibleRoutes() {
  return ROUTES.filter((rt) => map.hasLayer(rt.layer));
}

function updateRouteCount() {
  const n = visibleRoutes().length;
  const el = $('#routeCount');
  if (el) el.textContent = n + ' van ' + ROUTES.length + ' zichtbaar';
}

function fitVisible() {
  const vis = visibleRoutes();
  if (!vis.length) return;
  const pts = [];
  vis.forEach((rt) => pts.push(...rt.points));
  map.fitBounds(L.latLngBounds(pts).pad(0.1));
}

async function loadRoutes() {
  try {
    const r = await fetch(API + '/api/routes?limit=12');
    const routes = await r.json();
    if (!Array.isArray(routes) || !routes.length) {
      $('#map').innerHTML = '<p class="muted" style="padding:28px;text-align:center">Nog geen GPS-routes gevonden.</p>';
      return;
    }
    if (typeof L === 'undefined') {
      $('#map').innerHTML = '<p class="muted" style="padding:28px;text-align:center">Kaartbibliotheek kon niet geladen worden.</p>';
      return;
    }
    if (!map) {
      map = L.map('map', { scrollWheelZoom: false });
      // OpenStreetMap: geen API-key nodig. CARTO vereist die sinds kort wel en
      // stuurde in plaats van kaartdata een tegel met "API key needed".
      const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      });
      let tileFails = 0;
      tiles.on('tileerror', () => {
        tileFails += 1;
        if (tileFails === 4) {
          const w = $('#mapWarn');
          show(w, true, 'block');
          w.className = 'msg err';
          w.textContent = 'Kaarttegels laden niet. De routes staan er wel; alleen de ondergrond ontbreekt.';
        }
      });
      tiles.addTo(map);
      // Zet- en uitzetten via de regelaar op de kaart ook in de chips doorvoeren.
      map.on('overlayadd overlayremove', (e) => {
        const rt = ROUTES.find((x) => x.layer === e.layer);
        if (rt) setRoute(rt.id, e.type === 'overlayadd', false);
      });
    }

    // Oude lagen weg voordat we opnieuw opbouwen.
    ROUTES.forEach((rt) => { if (map.hasLayer(rt.layer)) map.removeLayer(rt.layer); });
    ROUTES = routes.map((rt, i) => {
      const color = ROUTE_COLORS[i % ROUTE_COLORS.length];
      const layer = L.polyline(rt.points, { color, weight: 3, opacity: .85 });
      layer.bindPopup('<b>' + rt.date + '</b><br>' + rt.km + ' km in ' + fmtMin(rt.minutes)
        + (rt.avg_hr ? '<br>gem. HR ' + Math.round(rt.avg_hr) : ''));
      return Object.assign({}, rt, { layer, color });
    });

    ROUTES.forEach((rt) => { if (isOn(rt.id)) rt.layer.addTo(map); });
    syncLayerControl();

    $('#routeList').innerHTML = ROUTES.map((rt) =>
      '<span class="routeChip ' + (isOn(rt.id) ? '' : 'off') + '" data-id="' + rt.id + '">'
      + '<label><input type="checkbox" ' + (isOn(rt.id) ? 'checked' : '') + '>'
      + '<span class="swatch" style="background:' + rt.color + '"></span>'
      + rt.date + ' · ' + rt.km + ' km · ' + fmtMin(rt.minutes) + '</label>'
      + '<button class="zoom" title="Inzoomen op deze route">&#9906;</button></span>').join('');

    fitVisible();
    updateRouteCount();
  } catch (e) {
    $('#map').innerHTML = '<p class="muted" style="padding:28px;text-align:center">Routes laden mislukte: ' + e.message + '</p>';
  }
}

// Eenmalig gezet, niet per loadRoutes - anders vuren de handlers dubbel.
document.addEventListener('change', (e) => {
  const chip = e.target.closest && e.target.closest('.routeChip');
  if (chip && e.target.matches('input[type=checkbox]')) {
    setRoute(chip.dataset.id, e.target.checked, true);
  }
});

document.addEventListener('click', (e) => {
  const zoom = e.target.closest && e.target.closest('.routeChip .zoom');
  if (zoom) {
    const rt = ROUTES.find((x) => String(x.id) === zoom.parentElement.dataset.id);
    if (rt && map.hasLayer(rt.layer)) { map.fitBounds(rt.layer.getBounds().pad(0.15)); rt.layer.openPopup(); }
    return;
  }
  if (e.target.id === 'btnRoutesAll') { ROUTES.forEach((rt) => setRoute(rt.id, true, false)); syncLayerControl(); fitVisible(); }
  if (e.target.id === 'btnRoutesNone') { ROUTES.forEach((rt) => setRoute(rt.id, false, false)); syncLayerControl(); }
  if (e.target.id === 'btnRoutesFit') fitVisible();
});

async function loadDiag() {
  try {
    const j = await (await fetch(API + '/api/health')).json();
    const rows = Object.entries(j).map(([k, v]) =>
      `<div class="diagRow"><span class="dot ${v.ok ? 'ok' : 'bad'}"></span>
        <b>${k}</b><span class="muted">${v.ok ? v.tools + ' tools bereikbaar' : v.error}</span></div>`);
    const m = STATE.metrics || {};
    Object.entries(m).forEach(([k, v]) => {
      if (!v.ok) rows.push(`<div class="diagRow"><span class="dot bad"></span><b>${k}</b><span class="muted">${v.error}</span></div>`);
    });
    $('#diag').innerHTML = rows.join('');
  } catch (e) { $('#diag').innerHTML = `<span class="muted">${e.message}</span>`; }
}

async function upload(payload, btn) {
  const msg = $('#uploadMsg');
  if (btn) { btn.disabled = true; btn.textContent = 'Bezig…'; }
  try {
    const r = await fetch(API + '/api/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    const fails = (j.results || []).filter((x) => !x.ok);
    show(msg, true, 'block');
    msg.className = 'msg ' + (fails.length ? 'err' : 'ok');
    msg.innerHTML = `${j.uploaded} van ${j.total} naar Garmin gezet en ingepland.` +
      (fails.length ? '<br>Mislukt: ' + fails.map((f) => `${f.key} (${f.error})`).join('; ') : '');
    await load(false);
  } catch (e) {
    show(msg, true, 'block'); msg.className = 'msg err';
    msg.textContent = 'Upload mislukte: ' + e.message;
    if (btn) { btn.disabled = false; btn.textContent = 'Naar Garmin'; }
  }
}

document.addEventListener('click', (e) => {
  const one = e.target.closest('button.up');
  if (one) return upload({ sessions: [{ date: one.dataset.date, kind: one.dataset.kind }] }, one);
  const wk = e.target.closest('button.upweek, #btnUploadWeek');
  if (wk) {
    const n = wk.dataset.week;
    if (confirm(`Alle trainingen van week ${n} in je Garmin-agenda zetten?`)) {
      return upload({ week: Number(n) }, wk);
    }
  }
});

$('#btnRefresh').addEventListener('click', () => load(true));

$('#btnAdapt').addEventListener('click', async (e) => {
  const b = e.target;
  b.disabled = true; b.textContent = 'Beoordelen…';
  try {
    const j = await (await fetch(API + '/api/adapt', { method: 'POST' })).json();
    if (!j.ok) throw new Error(j.error || 'onbekende fout');
    await load(false);
  } catch (err) {
    $('#adaptBody').innerHTML = `<div class="msg err">Beoordelen mislukte: ${err.message}</div>`;
  }
  b.disabled = false; b.textContent = 'Nu opnieuw beoordelen';
});

$('#btnGoal').addEventListener('click', () => {
  const g = STATE.goal, f = $('#goalForm');
  f.goal_name.value = g.goal_name;
  f.race_date.value = g.race_date;
  f.distance_km.value = g.distance_km;
  f.days_per_week.value = String(g.days_per_week);
  f.priority.value = g.priority;
  f.target_time_min.value = g.target_time_min || '';
  $('#goalDlg').showModal();
});

$('#goalDlg').addEventListener('close', async () => {
  if ($('#goalDlg').returnValue !== 'save') return;
  const f = $('#goalForm');
  await fetch(API + '/api/goal', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      goal_name: f.goal_name.value,
      race_date: f.race_date.value,
      distance_km: Number(f.distance_km.value),
      days_per_week: Number(f.days_per_week.value),
      priority: f.priority.value,
      target_time_min: f.target_time_min.value ? Number(f.target_time_min.value) : null,
    }),
  });
  load(false);
});

load(false);

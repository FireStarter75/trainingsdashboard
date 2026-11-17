'use strict';

/* De coach in de browser.
 *
 * Alles wat hier gebeurt is tekst heen en weer plus knoppen op voorstellen.
 * Een voorstel wordt nooit automatisch uitgevoerd: de knop stuurt het id terug
 * naar /api/chat/apply, dat het opnieuw valideert voordat er iets gebeurt.
 */

const cq = (s) => document.querySelector(s);
let COACH = { open: false, busy: false, chips: [], enabled: true, greeted: false };

const cEl = {
  fab: cq('#coachFab'),
  badge: cq('#coachBadge'),
  nudge: cq('#coachNudge'),
  nudgeText: cq('#coachNudgeText'),
  panel: cq('#coachPanel'),
  log: cq('#coachLog'),
  chips: cq('#coachChips'),
  form: cq('#coachForm'),
  input: cq('#coachInput'),
  send: cq('#coachSend'),
  state: cq('#coachState'),
};

function cShow(el, on, mode) {
  if (!el) return;
  el.hidden = !on;
  el.style.display = on ? (mode || '') : 'none';
}

function cState(mode, line) {
  cEl.panel.classList.remove('is-thinking', 'is-talking', 'is-idle');
  cEl.panel.classList.add('is-' + mode);
  if (line) cEl.state.textContent = line;
}

/* Tekst van de bot: eerst alles ontsmetten, daarna een paar opmaakregels.
 * Geen HTML uit het model doorlaten, ook niet onbedoeld. */
function cFmt(t) {
  const esc = String(t == null ? '' : t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>');
}

function cBubble(role, text, cls) {
  const d = document.createElement('div');
  d.className = 'cmsg ' + (cls || (role === 'user' ? 'me' : 'bot'));
  d.innerHTML = cFmt(text);
  cEl.log.appendChild(d);
  cScroll();
  return d;
}

function cScroll() {
  requestAnimationFrame(() => { cEl.log.scrollTop = cEl.log.scrollHeight; });
}

function cTyping(on) {
  const old = cq('#cTyping');
  if (old) old.remove();
  if (!on) return;
  const d = document.createElement('div');
  d.id = 'cTyping';
  d.className = 'ctyping';
  d.innerHTML = '<i></i><i></i><i></i>';
  cEl.log.appendChild(d);
  cScroll();
}

/* ---------------------------------------------------------- voorstelkaartjes */

function cActionCard(a) {
  const card = document.createElement('div');
  card.className = 'cact' + (a.status === 'applied' ? ' done' : a.status === 'pending' ? '' : ' no');
  card.dataset.id = a.id;
  const btns = a.status === 'pending'
    ? `<div class="cactBtns">
         <button class="btn small cactYes">Doorvoeren</button>
         <button class="btn small ghost cactNo">Laat maar</button>
       </div>`
    : `<div class="cactMsg muted">${a.status === 'applied' ? 'Doorgevoerd.'
        : a.status === 'rejected' ? 'Niet doorgevoerd.'
        : 'Niet meer geldig.'}</div>`;
  card.innerHTML = `<h4>${cFmt(a.title)}</h4><p>${cFmt(a.detail)}</p>${btns}`;
  cEl.log.appendChild(card);
  cScroll();
  return card;
}

async function cApply(card, decision) {
  const id = card.dataset.id;
  card.querySelectorAll('button').forEach((b) => { b.disabled = true; });
  try {
    const r = await fetch('/api/chat/apply', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, decision }),
    });
    const j = await r.json();
    const box = card.querySelector('.cactBtns');
    if (j.error) {
      if (box) box.outerHTML = `<div class="cactMsg bad">${cFmt(j.error)}</div>`;
      card.classList.add('no');
      return;
    }
    if (box) {
      box.outerHTML = `<div class="cactMsg ${j.ok ? 'good' : 'muted'}">` +
        cFmt(j.message || (decision === 'reject' ? 'Niet doorgevoerd.' : 'Gelukt.')) + '</div>';
    }
    card.classList.add(j.status === 'applied' ? 'done' : 'no');
    // Het dashboard eronder moet het meteen laten zien; load() komt uit app.js.
    if (j.status === 'applied' && typeof load === 'function') load(false);
  } catch (e) {
    const box = card.querySelector('.cactBtns');
    if (box) box.outerHTML = `<div class="cactMsg bad">Mislukt: ${cFmt(e.message)}</div>`;
  }
}

cEl.log.addEventListener('click', (e) => {
  const yes = e.target.closest('.cactYes');
  if (yes) return cApply(yes.closest('.cact'), 'apply');
  const no = e.target.closest('.cactNo');
  if (no) return cApply(no.closest('.cact'), 'reject');
});

/* ------------------------------------------------------------------ chips */

function cRenderChips() {
  cEl.chips.innerHTML = '';
  COACH.chips.forEach((t) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = t;
    b.addEventListener('click', () => {
      COACH.chips = COACH.chips.filter((x) => x !== t);
      cRenderChips();
      cSend(t);
    });
    cEl.chips.appendChild(b);
  });
  cShow(cEl.chips, COACH.chips.length > 0, 'flex');
}

/* ------------------------------------------------------------- versturen */

async function cSend(text) {
  const msg = (text || cEl.input.value || '').trim();
  if (!msg || COACH.busy) return;
  COACH.busy = true;
  cEl.input.value = '';
  cEl.input.style.height = '';
  cEl.send.disabled = true;
  cBubble('user', msg);
  cTyping(true);
  cState('thinking', 'denkt na…');

  try {
    const r = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const j = await r.json();
    cTyping(false);
    if (j.error) {
      cBubble('coach', j.error, 'err');
      cState('idle', 'er ging iets mis');
    } else {
      cBubble('coach', j.reply);
      (j.actions || []).forEach(cActionCard);
      if ((j.dropped || []).length) {
        cBubble('coach', 'Eén voorstel van de coach viel buiten zijn grenzen en is ' +
          'weggegooid: ' + j.dropped.join('; '), 'err');
      }
      cState('talking', 'klaar voor je vraag');
      setTimeout(() => { if (!COACH.busy) cState('idle', 'klaar voor je vraag'); }, 2600);
    }
  } catch (e) {
    cTyping(false);
    cBubble('coach', 'Ik kon de coach niet bereiken: ' + e.message, 'err');
    cState('idle', 'niet bereikbaar');
  }
  COACH.busy = false;
  cEl.send.disabled = false;
  cEl.input.focus();
}

cEl.form.addEventListener('submit', (e) => { e.preventDefault(); cSend(); });

cEl.input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); cSend(); }
});

// Meegroeiend invoerveld, want een logje van drie regels is normaal.
cEl.input.addEventListener('input', () => {
  cEl.input.style.height = 'auto';
  cEl.input.style.height = Math.min(130, cEl.input.scrollHeight) + 'px';
});

/* --------------------------------------------------------- openen/sluiten */

function cOpen() {
  COACH.open = true;
  cShow(cEl.panel, true, 'flex');
  cShow(cEl.fab, false);
  cShow(cEl.nudge, false);
  cShow(cEl.badge, false);
  cState('idle', 'klaar voor je vraag');
  if (window.matchMedia('(min-width:641px)').matches) cEl.input.focus();
  cScroll();
}

function cClose() {
  COACH.open = false;
  cShow(cEl.panel, false);
  cShow(cEl.fab, true, 'grid');
}

cEl.fab.addEventListener('click', cOpen);
cq('#coachClose').addEventListener('click', cClose);
cEl.nudge.addEventListener('click', (e) => {
  if (e.target.closest('#coachNudgeClose')) return;
  cOpen();
});
cq('#coachNudgeClose').addEventListener('click', (e) => {
  e.stopPropagation();
  cShow(cEl.nudge, false);
  try { localStorage.setItem('coachNudgeSeen', new Date().toISOString().slice(0, 10)); }
  catch (err) { /* privémodus: dan maar elke keer */ }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && COACH.open) cClose();
});

cq('#coachClear').addEventListener('click', async () => {
  if (!confirm('Het hele gesprek wissen? Je logboek en je plan blijven staan.')) return;
  await fetch('/api/chat/clear', { method: 'POST' });
  cEl.log.innerHTML = '';
  COACH.greeted = false;
  cBoot(true);
});

/* ------------------------------------------------------------------ start */

function cFirstSentence(t) {
  const s = String(t || '').split('\n')[0];
  return s.length > 150 ? s.slice(0, 147) + '…' : s;
}

async function cBoot(force) {
  try {
    const j = await (await fetch('/api/chat/opening')).json();
    if (j.enabled === false) {
      COACH.enabled = false;
      cShow(cEl.fab, false);
      console.warn('coach staat uit:', j.reason);
      return;
    }
    (j.history || []).forEach((h) => {
      cBubble(h.role === 'user' ? 'user' : 'coach', h.text);
      (h.actions || []).forEach(cActionCard);
    });
    if (j.text) {
      cBubble('coach', j.text);
      COACH.greeted = true;
    }
    COACH.chips = j.chips || [];
    cRenderChips();

    // Zelf om de aandacht vragen, maar niet opdringerig: één wolkje per dag.
    let seen = null;
    try { seen = localStorage.getItem('coachNudgeSeen'); } catch (e) { seen = null; }
    const today = new Date().toISOString().slice(0, 10);
    if (!COACH.open && (force || seen !== today) && j.text) {
      setTimeout(() => {
        if (COACH.open) return;
        cEl.nudgeText.textContent = cFirstSentence(j.text.replace(/\*\*/g, ''));
        cShow(cEl.nudge, true, 'block');
        cEl.fab.classList.add('is-waving');
        setTimeout(() => cEl.fab.classList.remove('is-waving'), 2500);
      }, 5000);
    }
  } catch (e) {
    console.warn('coach kon niet starten', e);
  }
}

cShow(cEl.fab, true, 'grid');
cBoot(false);

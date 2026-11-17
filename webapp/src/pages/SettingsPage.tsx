import { useState } from 'react';
import { LogOut, ArrowLeft } from 'lucide-react';
import type { State, GoalConfig } from '../lib/types';
import { saveGoal, logout } from '../lib/api';

/* Instellingen: je doel wijzigen (via de bestaande /api/goal), plus de weg
   terug naar de klassieke interface. */
export function SettingsPage({ state, onChanged }: { state: State; onChanged: () => void }) {
  const cfg = state.plan.config;
  const [form, setForm] = useState<GoalConfig>({
    goal_name: cfg.goal_name,
    race_date: cfg.race_date,
    distance_km: cfg.distance_km,
    days_per_week: cfg.days_per_week,
    priority: cfg.priority,
    target_time_min: cfg.target_time_min ?? null,
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const set = <K extends keyof GoalConfig>(k: K, v: GoalConfig[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await saveGoal(form);
      setMsg('Opgeslagen — het plan is opnieuw opgebouwd.');
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <div className="rounded-3xl border border-white/10 bg-card/90 p-6">
        <h3 className="font-semibold tracking-tight text-zinc-100">Je doel</h3>
        <p className="mt-1 text-xs text-zinc-500">
          Wijzigen bouwt het hele plan opnieuw op., ook voor toekomstige doelen bruikbaar.
        </p>
        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-xs text-zinc-500">Naam</span>
            <input
              value={form.goal_name}
              onChange={(e) => set('goal_name', e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-lime-500/50"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-zinc-500">Racedatum</span>
              <input
                type="date"
                value={form.race_date}
                onChange={(e) => set('race_date', e.target.value)}
                className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-lime-500/50"
              />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Afstand (km)</span>
              <input
                inputMode="decimal"
                value={form.distance_km}
                onChange={(e) => set('distance_km', Number(e.target.value.replace(',', '.')) || 0)}
                className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-lime-500/50"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-zinc-500">Trainingen per week</span>
              <input
                inputMode="numeric"
                value={form.days_per_week}
                onChange={(e) => set('days_per_week', Number(e.target.value) || 0)}
                className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-lime-500/50"
              />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">Streeftijd (min, leeg = geen)</span>
              <input
                inputMode="numeric"
                value={form.target_time_min ?? ''}
                onChange={(e) => set('target_time_min', e.target.value ? Number(e.target.value) : null)}
                className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-lime-500/50"
              />
            </label>
          </div>
          <label className="block">
            <span className="text-xs text-zinc-500">Prioriteit</span>
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              {(['health', 'time'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => set('priority', p)}
                  className={`rounded-xl border px-3 py-2 text-sm transition-colors ${
                    form.priority === p
                      ? 'border-lime-500/50 bg-lime-500/15 text-lime-300'
                      : 'border-white/10 bg-white/5 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {p === 'health' ? 'Gezond finishen' : 'Streeftijd'}
                </button>
              ))}
            </div>
          </label>
        </div>
        {msg && <p className="mt-4 text-xs text-lime-300">{msg}</p>}
        <button
          disabled={busy}
          onClick={() => void save()}
          className="mt-5 w-full rounded-xl bg-lime-500 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-50"
        >
          {busy ? 'Bezig…' : 'Opslaan'}
        </button>
      </div>

      <div className="rounded-3xl border border-white/10 bg-card/90 p-6">
        <h3 className="font-semibold tracking-tight text-zinc-100">Overig</h3>
        <div className="mt-4 space-y-2">
          <a
            href={(window as unknown as { __API_BASE__?: string }).__API_BASE__ || '/'}
            className="flex items-center gap-3 rounded-xl border border-white/10 px-4 py-3 text-sm text-zinc-300 hover:bg-white/5"
          >
            <ArrowLeft size={16} /> Klassieke interface openen (met kaart en coach)
          </a>
          <button
            onClick={() => void logout()}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 px-4 py-3 text-sm text-zinc-300 hover:bg-white/5"
          >
            <LogOut size={16} /> Uitloggen
          </button>
        </div>
      </div>
    </div>
  );
}

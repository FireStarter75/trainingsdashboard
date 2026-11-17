import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import type { State } from './lib/types';
import { fetchState, API_BASE } from './lib/api';
import { Sidebar, type View } from './components/Sidebar';
import { BottomNav } from './components/BottomNav';
import { Dashboard } from './pages/Dashboard';
import { PlanPage } from './pages/PlanPage';
import { StatsPage } from './pages/StatsPage';
import { SettingsPage } from './pages/SettingsPage';

export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>('dashboard');

  const load = () => {
    fetchState()
      .then((s) => {
        setState(s);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof Error && e.message !== 'niet ingelogd') setErr(e.message);
      });
  };

  useEffect(load, []);

  const refresh = () => {
    fetch(API_BASE + '/api/state?refresh=1', { method: 'POST' }).catch(() => undefined);
    load();
  };

  if (err) {
    return (
      <div className="grid min-h-dvh place-items-center p-6 text-center">
        <div>
          <p className="text-sm text-zinc-400">{err}</p>
          <button onClick={load} className="mt-4 rounded-xl bg-lime-500 px-5 py-2.5 text-sm font-semibold text-zinc-950">
            Opnieuw
          </button>
        </div>
      </div>
    );
  }

  if (!state) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <div className="flex flex-col items-center gap-4 text-zinc-500">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-zinc-800 border-t-lime-500" />
          <p className="text-sm">Data ophalen uit Garmin…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-canvas text-zinc-100">
      {/* Achtergrondgloed */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/4 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-lime-500/[0.05] blur-3xl" />
        <div className="absolute -top-24 right-0 h-80 w-[36rem] rounded-full bg-sky-500/[0.04] blur-3xl" />
      </div>

      <Sidebar view={view} onSelect={setView} />

      <div className="md:pl-64">
        <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-canvas/70 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-8">
            <div className="flex items-center gap-2.5 md:hidden">
              <span className="h-2 w-2 rounded-full bg-lime-400 shadow-[0_0_12px_2px_rgba(132,204,22,0.35)]" />
              <span className="font-semibold tracking-tight">dash</span>
            </div>
            <div className="hidden md:block">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {state.plan.config.goal_name}
              </p>
              <p className="tabular text-xs text-zinc-500">
                {state.plan.config.distance_km} km · week {state.plan.weeks.find((w) => w.start <= state.today && state.today <= w.end)?.index ?? '–'} van {state.plan.weeks.length}
              </p>
            </div>
            <motion.button
              whileTap={{ scale: 0.96 }}
              onClick={refresh}
              className="rounded-xl border border-white/10 px-3.5 py-2 text-xs font-medium text-zinc-300 hover:border-white/20 hover:bg-white/5"
            >
              Verversen
            </motion.button>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 pb-32 pt-6 md:px-8 md:pb-16">
          {view === 'dashboard' && <Dashboard state={state} onChanged={load} />}
          {view === 'schema' && <PlanPage state={state} />}
          {view === 'statistieken' && <StatsPage state={state} />}
          {view === 'instellingen' && <SettingsPage state={state} onChanged={load} />}
        </main>
      </div>

      <BottomNav view={view} onSelect={setView} />
    </div>
  );
}

import { Activity, CalendarDays, BarChart3, Settings, LogOut } from 'lucide-react';
import { logout } from '../lib/api';

export type View = 'dashboard' | 'schema' | 'statistieken' | 'instellingen';

export const NAV: { key: View; label: string; icon: typeof Activity }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboardIcon },
  { key: 'schema', label: 'Schema', icon: CalendarDays },
  { key: 'statistieken', label: 'Statistieken', icon: BarChart3 },
  { key: 'instellingen', label: 'Instellingen', icon: Settings },
];

function LayoutDashboardIcon(props: { className?: string }) {
  return <Activity {...props} />;
}

export function Sidebar({ view, onSelect }: { view: View; onSelect: (v: View) => void }) {
  return (
    <aside className="hidden md:flex fixed inset-y-0 left-0 w-64 flex-col border-r border-white/10 bg-zinc-950/60 backdrop-blur-xl z-40">
      <div className="flex items-center gap-2.5 px-6 h-16 border-b border-white/10">
        <span className="h-2 w-2 rounded-full bg-lime-400 shadow-[0_0_12px_2px_rgba(132,204,22,0.35)]" />
        <span className="font-semibold tracking-tight text-zinc-100">dash</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map((it) => (
          <button
            key={it.key}
            onClick={() => onSelect(it.key)}
            className={`w-full flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm transition-colors ${
              view === it.key
                ? 'bg-lime-500/10 text-lime-300 border border-lime-500/20'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <it.icon size={17} strokeWidth={1.8} />
            {it.label}
          </button>
        ))}
      </nav>
      <div className="px-3 pb-5">
        <button
          onClick={() => void logout()}
          className="w-full flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors"
        >
          <LogOut size={16} strokeWidth={1.8} />
          Uitloggen
        </button>
      </div>
    </aside>
  );
}

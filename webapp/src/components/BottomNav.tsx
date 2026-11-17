import { NAV, type View } from './Sidebar';

/* Zwevende glassmorphic balk onderaan (mobiel), met één duim bedienbaar. */
export function BottomNav({ view, onSelect }: { view: View; onSelect: (v: View) => void }) {
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 px-3 pb-3 pt-2">
      <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-zinc-900/80 backdrop-blur-xl shadow-2xl shadow-black/50">
        <div className="grid grid-cols-4">
          {NAV.map((it) => {
            const active = view === it.key;
            return (
              <button
                key={it.key}
                onClick={() => onSelect(it.key)}
                className={`flex flex-col items-center gap-1 py-2.5 rounded-xl text-[10.5px] font-medium transition-colors ${
                  active ? 'text-lime-300' : 'text-zinc-500 active:text-zinc-300'
                }`}
              >
                <it.icon size={19} strokeWidth={active ? 2.2 : 1.8} />
                {it.label}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

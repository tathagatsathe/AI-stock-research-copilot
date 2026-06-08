import React from 'react';
import { Search, Sparkles } from 'lucide-react';

export default function SymbolSearchDropdown({
  suggestions,
  loading,
  highlightIndex,
  onSelect,
  onHighlight,
}) {
  if (!loading && suggestions.length === 0) return null;

  return (
    <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-50 rounded-xl border border-neutral-700 bg-neutral-900/95 backdrop-blur-xl shadow-2xl overflow-hidden">
      {loading && suggestions.length === 0 && (
        <div className="px-4 py-3 text-xs text-neutral-400">Finding symbols...</div>
      )}
      <ul className="max-h-72 overflow-y-auto py-1">
        {suggestions.map((item, index) => {
          const active = index === highlightIndex;
          return (
            <li key={`${item.source}-${item.ticker}`}>
              <button
                type="button"
                onMouseEnter={() => onHighlight(index)}
                onClick={() => onSelect(item)}
                className={`w-full text-left px-4 py-2.5 transition-colors ${
                  active
                    ? 'bg-accent-cyan/15 text-white'
                    : 'hover:bg-neutral-800/80 text-neutral-200'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">
                        {item.display_ticker || item.ticker}
                      </span>
                      {item.in_universe ? (
                        <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-neutral-700 text-neutral-300">
                          Universe
                        </span>
                      ) : (
                        <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20">
                          Yahoo
                        </span>
                      )}
                    </div>
                    {item.name && (
                      <p className="text-xs text-neutral-400 truncate mt-0.5">{item.name}</p>
                    )}
                  </div>
                  {item.source === 'remote' ? (
                    <Sparkles className="w-3.5 h-3.5 text-accent-purple shrink-0" />
                  ) : (
                    <Search className="w-3.5 h-3.5 text-neutral-500 shrink-0" />
                  )}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

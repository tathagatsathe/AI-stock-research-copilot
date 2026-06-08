const YAHOO_SUFFIX_RE = /[.=^/-]/;

/** Normalize user input into a Yahoo Finance symbol for the active market tab. */
export function prepareCustomTicker(query, market = 'us_stocks') {
  const trimmed = query.trim().toUpperCase();
  if (!trimmed) return '';

  if (YAHOO_SUFFIX_RE.test(trimmed)) {
    return trimmed;
  }

  if (market === 'india_stocks') {
    return `${trimmed}.NS`;
  }

  return trimmed;
}

/** Mirror of backend display_ticker for loading/custom-ticker states. */
export function formatDisplayTicker(symbol) {
  if (!symbol) return '';
  const normalized = symbol.trim().toUpperCase();
  if (normalized.startsWith('^')) return normalized.slice(1);
  if (normalized.endsWith('.NS') || normalized.endsWith('.BO')) {
    return normalized.split('.')[0];
  }
  if (normalized.endsWith('=X')) {
    const pair = normalized.slice(0, -2);
    if (pair.length === 6) return `${pair.slice(0, 3)}/${pair.slice(3)}`;
    return pair;
  }
  if (normalized.endsWith('=F')) return normalized.slice(0, -2);
  if (normalized.endsWith('-USD')) return normalized.slice(0, -4);
  return normalized;
}

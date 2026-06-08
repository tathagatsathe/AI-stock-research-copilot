import React, { useMemo } from 'react';

const CHART_WIDTH = 640;
const CHART_HEIGHT = 220;
const PADDING = { top: 16, right: 16, bottom: 32, left: 56 };

function rollingSma(closes, period) {
  return closes.map((_, index) => {
    if (index < period - 1) return null;
    const slice = closes.slice(index - period + 1, index + 1);
    return slice.reduce((sum, value) => sum + value, 0) / period;
  });
}

function formatPrice(value) {
  if (value >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (value >= 100) return value.toFixed(1);
  return value.toFixed(2);
}

function formatDateLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00:00`);
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function PriceChart({ data, smaPeriod = 50, loading = false }) {
  const chart = useMemo(() => {
    if (!data?.length) return null;

    const closes = data.map((point) => point.close);
    const sma = rollingSma(closes, smaPeriod);
    const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
    const plotHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;

    const minPrice = Math.min(...closes);
    const maxPrice = Math.max(...closes);
    const range = maxPrice - minPrice || 1;

    const toX = (index) =>
      PADDING.left + (index / Math.max(data.length - 1, 1)) * plotWidth;
    const toY = (price) =>
      PADDING.top + plotHeight - ((price - minPrice) / range) * plotHeight;

    const pricePath = data
      .map((point, index) => `${index === 0 ? 'M' : 'L'} ${toX(index)} ${toY(point.close)}`)
      .join(' ');

    const areaPath = `${pricePath} L ${toX(data.length - 1)} ${PADDING.top + plotHeight} L ${toX(0)} ${PADDING.top + plotHeight} Z`;

    const smaSegments = [];
    let segment = [];
    sma.forEach((value, index) => {
      if (value === null) return;
      const point = `${toX(index)} ${toY(value)}`;
      segment.push(point);
      const next = sma[index + 1];
      if (next === null || index === sma.length - 1) {
        if (segment.length > 1) {
          smaSegments.push(`M ${segment.join(' L ')}`);
        }
        segment = [];
      }
    });

    const firstDate = data[0]?.date;
    const lastDate = data[data.length - 1]?.date;
    const startPrice = closes[0];
    const endPrice = closes[closes.length - 1];
    const changePct = startPrice ? ((endPrice / startPrice - 1) * 100) : 0;

    return {
      pricePath,
      areaPath,
      smaSegments,
      minPrice,
      maxPrice,
      firstDate,
      lastDate,
      changePct,
      yTicks: [minPrice, minPrice + range / 2, maxPrice],
    };
  }, [data, smaPeriod]);

  if (loading) {
    return (
      <div className="bg-neutral-800/40 rounded-xl p-6 border border-neutral-700/50">
        <div className="h-[220px] rounded-lg bg-neutral-800/60 animate-pulse" />
      </div>
    );
  }

  if (!chart) return null;

  const changePositive = chart.changePct >= 0;

  return (
    <div className="bg-neutral-800/40 rounded-xl p-6 border border-neutral-700/50">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">6-Month Price</h3>
          <p className="text-xs text-neutral-400 mt-0.5">Daily close with 50-day SMA</p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-neutral-300">
            <span className="w-3 h-0.5 bg-accent-cyan rounded-full" />
            Price
          </span>
          <span className="flex items-center gap-1.5 text-neutral-300">
            <span className="w-3 h-0.5 bg-accent-purple rounded-full" />
            SMA 50
          </span>
          <span className={`font-semibold ${changePositive ? 'text-green-400' : 'text-red-400'}`}>
            {changePositive ? '+' : ''}{chart.changePct.toFixed(2)}% (6M)
          </span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        className="w-full h-auto"
        role="img"
        aria-label="Six month price chart"
      >
        <defs>
          <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </linearGradient>
        </defs>

        {chart.yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PADDING.left}
              y1={PADDING.top + (CHART_HEIGHT - PADDING.top - PADDING.bottom) - ((tick - chart.minPrice) / (chart.maxPrice - chart.minPrice || 1)) * (CHART_HEIGHT - PADDING.top - PADDING.bottom)}
              x2={CHART_WIDTH - PADDING.right}
              y2={PADDING.top + (CHART_HEIGHT - PADDING.top - PADDING.bottom) - ((tick - chart.minPrice) / (chart.maxPrice - chart.minPrice || 1)) * (CHART_HEIGHT - PADDING.top - PADDING.bottom)}
              stroke="#404040"
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <text
              x={PADDING.left - 8}
              y={PADDING.top + (CHART_HEIGHT - PADDING.top - PADDING.bottom) - ((tick - chart.minPrice) / (chart.maxPrice - chart.minPrice || 1)) * (CHART_HEIGHT - PADDING.top - PADDING.bottom) + 4}
              textAnchor="end"
              fill="#a3a3a3"
              fontSize="10"
            >
              {formatPrice(tick)}
            </text>
          </g>
        ))}

        <path d={chart.areaPath} fill="url(#priceFill)" />
        <path d={chart.pricePath} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

        {chart.smaSegments.map((segment, index) => (
          <path
            key={index}
            d={segment}
            fill="none"
            stroke="#a855f7"
            strokeWidth="1.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity="0.9"
          />
        ))}

        <text x={PADDING.left} y={CHART_HEIGHT - 10} fill="#a3a3a3" fontSize="10">
          {formatDateLabel(chart.firstDate)}
        </text>
        <text x={CHART_WIDTH - PADDING.right} y={CHART_HEIGHT - 10} fill="#a3a3a3" fontSize="10" textAnchor="end">
          {formatDateLabel(chart.lastDate)}
        </text>
      </svg>
    </div>
  );
}

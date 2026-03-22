import React from 'react';
import PropTypes from 'prop-types';
import { ResponsiveContainer, LineChart, Line, Tooltip } from 'recharts';

function sparklineColor(sentiment) {
  if (sentiment === 'bullish') return '#10b981';
  if (sentiment === 'bearish') return '#ef4444';
  return '#f59e0b';
}

export default function PriceSparkline({ priceHistory, sentiment }) {
  if (!priceHistory || priceHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-12 text-gray-700 font-mono-data text-xs">
        No price data
      </div>
    );
  }

  const color = sparklineColor(sentiment);
  const data = priceHistory.map(p => ({ close: p.close }));

  return (
    <ResponsiveContainer width="100%" height={48}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
        <Line
          type="monotone"
          dataKey="close"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={true}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#111827',
            border: '1px solid #374151',
            borderRadius: '4px',
            padding: '4px 8px',
            fontSize: '11px',
            fontFamily: 'IBM Plex Mono',
          }}
          labelStyle={{ display: 'none' }}
          formatter={(v) => [`$${v.toFixed(2)}`, '']}
          itemStyle={{ color }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

PriceSparkline.propTypes = {
  priceHistory: PropTypes.arrayOf(PropTypes.shape({
    date: PropTypes.string,
    close: PropTypes.number,
  })),
  sentiment: PropTypes.string,
};

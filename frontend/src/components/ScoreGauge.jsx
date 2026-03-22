import React from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

function scoreColor(score) {
  if (score >= 65) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

export default function ScoreGauge({ score, size = 96, strokeWidth = 8 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(100, Math.max(0, score)) / 100;
  const dashOffset = circumference * (1 - pct);
  const color = scoreColor(score);
  const center = size / 2;
  const filterId = `glow-${size}-${Math.round(score)}`;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      {/*
        overflow: visible lets the glow bleed outside the SVG viewport.
        The SVG filter approach keeps the glow arc-shaped (no square artifact).
      */}
      <svg
        width={size}
        height={size}
        overflow="visible"
        style={{ transform: 'rotate(-90deg)' }}
      >
        <defs>
          <filter id={filterId} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
            <feColorMatrix in="blur" type="saturate" values="3" result="sat" />
            <feMerge>
              <feMergeNode in="sat" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Track */}
        <circle
          cx={center} cy={center} r={radius}
          fill="none"
          stroke="#1f2937"
          strokeWidth={strokeWidth}
        />

        {/* Glow layer — blurred duplicate arc, arc-shaped so no square */}
        <motion.circle
          cx={center} cy={center} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth + 6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.2 }}
          style={{ opacity: 0.35, filter: 'blur(5px)' }}
        />

        {/* Progress arc */}
        <motion.circle
          cx={center} cy={center} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.2 }}
        />
      </svg>

      {/* Score label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <motion.span
          className="font-mono-data font-semibold leading-none"
          style={{ color, fontSize: size * 0.22 }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6, duration: 0.4 }}
        >
          {Math.round(score)}
        </motion.span>
        <span className="font-sans text-gray-500 leading-none mt-0.5" style={{ fontSize: size * 0.1 }}>
          /100
        </span>
      </div>
    </div>
  );
}

ScoreGauge.propTypes = {
  score: PropTypes.number.isRequired,
  size: PropTypes.number,
  strokeWidth: PropTypes.number,
};

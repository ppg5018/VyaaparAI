'use client';

import { useEffect, useRef, useState } from 'react';

interface GaugeProps {
  score: number;
  band: 'green' | 'yellow' | 'red';
}

const R = 80;
const CX = 100;
const CY = 100;
// Semicircle arc length: π × R
const ARC_LEN = Math.PI * R;

// M left A ... 0 0 0 right → counter-clockwise = top half of circle
const ARC_PATH = `M ${CX - R} ${CY} A ${R} ${R} 0 0 0 ${CX + R} ${CY}`;

const BAND_COLOR: Record<GaugeProps['band'], string> = {
  green:  'var(--emerald)',
  yellow: 'var(--yellow)',
  red:    'var(--red)',
};

const BAND_LABEL: Record<GaugeProps['band'], string> = {
  green:  'Healthy',
  yellow: 'Needs Attention',
  red:    'Critical',
};

// Ease-out cubic
function easeOut(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export default function Gauge({ score, band }: GaugeProps) {
  const [displayed, setDisplayed] = useState(0);
  const [dashOffset, setDashOffset] = useState(ARC_LEN);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const duration = 1400;

    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const e = easeOut(t);
      setDisplayed(Math.round(e * score));
      setDashOffset(ARC_LEN * (1 - (e * score) / 100));
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [score]);

  const color = BAND_COLOR[band];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <svg
        viewBox="0 0 200 110"
        width={200}
        height={110}
        style={{ overflow: 'visible' }}
      >
        {/* Track */}
        <path
          d={ARC_PATH}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={12}
          strokeLinecap="round"
        />
        {/* Progress arc */}
        <path
          d={ARC_PATH}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={ARC_LEN}
          strokeDashoffset={dashOffset}
        />
        {/* Score number */}
        <text
          x={CX}
          y={72}
          textAnchor="middle"
          fill="var(--text)"
          fontSize={42}
          fontFamily="var(--font-space-grotesk), sans-serif"
          fontWeight={700}
          letterSpacing="-1"
        >
          {displayed}
        </text>
        {/* /100 label */}
        <text
          x={CX}
          y={92}
          textAnchor="middle"
          fill="var(--text3)"
          fontSize={11}
          fontFamily="var(--font-space-grotesk), sans-serif"
          fontWeight={400}
        >
          /100
        </text>
      </svg>

      {/* Band label */}
      <span
        style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color,
        }}
      >
        {BAND_LABEL[band]}
      </span>
    </div>
  );
}

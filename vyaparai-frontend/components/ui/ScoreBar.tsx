'use client';

import { useEffect, useState } from 'react';

interface ScoreBarProps {
  label: string;
  val: number;
  weight: number;
  color: string;
}

export default function ScoreBar({ label, val, weight, color }: ScoreBarProps) {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    // Defer one frame so CSS transition fires from 0
    const id = requestAnimationFrame(() => setWidth(val));
    return () => cancelAnimationFrame(id);
  }, [val]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 13, color: 'var(--text2)' }}>{label}</span>
          <span
            style={{
              fontSize: 10,
              color: 'var(--text3)',
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '1px 5px',
            }}
          >
            {weight}%
          </span>
        </div>
        <span
          style={{
            fontFamily: 'var(--font-space-mono), monospace',
            fontWeight: 700,
            fontSize: 13,
            color: 'var(--text)',
          }}
        >
          {val}
        </span>
      </div>

      <div
        style={{
          width: '100%',
          height: 5,
          background: 'rgba(255,255,255,0.06)',
          borderRadius: 999,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${width}%`,
            height: '100%',
            background: color,
            borderRadius: 999,
            transition: 'width 900ms cubic-bezier(0.4,0,0.2,1)',
          }}
        />
      </div>
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';

interface BarDatum {
  week: string;
  rev: number;
}

interface BarsProps {
  data: BarDatum[];
  height?: number;
}

export default function Bars({ data, height = 80 }: BarsProps) {
  const [mounted, setMounted] = useState(false);
  const [hovered, setHovered] = useState<number | null>(null);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const maxRev = Math.max(1, ...data.map((d) => d.rev));

  return (
    <div>
      {/* Bar columns */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 3,
          height,
        }}
      >
        {data.map((d, i) => {
          const barH = Math.max(2, (d.rev / maxRev) * height);

          return (
            <div
              key={i}
              style={{
                flex: 1,
                height,
                position: 'relative',
                cursor: 'default',
              }}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Hover tooltip */}
              {hovered === i && (
                <div
                  style={{
                    position: 'absolute',
                    bottom: barH + 6,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    background: 'var(--surface2)',
                    border: '1px solid var(--border2)',
                    borderRadius: 5,
                    padding: '2px 7px',
                    fontSize: 10,
                    fontFamily: 'var(--font-space-mono), monospace',
                    color: 'var(--text)',
                    whiteSpace: 'nowrap',
                    zIndex: 10,
                    pointerEvents: 'none',
                  }}
                >
                  ₹{d.rev.toLocaleString('en-IN')}
                </div>
              )}

              {/* Bar */}
              <div
                style={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: mounted ? barH : 0,
                  background: 'var(--violet)',
                  opacity: hovered === i ? 1 : 0.6,
                  borderRadius: '3px 3px 0 0',
                  transition: `height 600ms cubic-bezier(0.4,0,0.2,1) ${i * 40}ms, opacity 150ms`,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Week labels */}
      <div style={{ display: 'flex', gap: 3, marginTop: 5 }}>
        {data.map((d, i) => (
          <span
            key={i}
            style={{
              flex: 1,
              textAlign: 'center',
              fontSize: 9,
              fontFamily: 'var(--font-space-mono), monospace',
              color: 'var(--text3)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {d.week}
          </span>
        ))}
      </div>
    </div>
  );
}

import { Fragment } from 'react';

interface StepsProps {
  active: number;
}

const STEP_LABELS = ['Account', 'POS', 'Business', 'Preferences', 'Dashboard'];

function CheckIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 12 12" fill="none" stroke="#000" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2,6 5,9 10,3" />
    </svg>
  );
}

export default function Steps({ active }: StepsProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start' }}>
      {STEP_LABELS.map((label, i) => {
        const isCompleted = i < active;
        const isActive    = i === active;
        const isFuture    = i > active;

        return (
          <Fragment key={i}>
            {/* Step circle + label */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 5,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: isCompleted || isActive ? 'var(--gold)' : 'transparent',
                  border: `1.5px solid ${isFuture ? 'var(--text3)' : 'var(--gold)'}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 600,
                  color: isCompleted || isActive ? '#000' : 'var(--text3)',
                  flexShrink: 0,
                  fontFamily: 'var(--font-space-grotesk), sans-serif',
                  transition: 'background 250ms, border-color 250ms',
                }}
              >
                {isCompleted ? <CheckIcon /> : i + 1}
              </div>

              <span
                style={{
                  fontSize: 10,
                  fontWeight: isActive ? 600 : 400,
                  color: isFuture ? 'var(--text3)' : 'var(--gold)',
                  whiteSpace: 'nowrap',
                  transition: 'color 250ms',
                }}
              >
                {label}
              </span>
            </div>

            {/* Connector line between steps */}
            {i < STEP_LABELS.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 1.5,
                  background: i < active ? 'var(--gold)' : 'var(--border)',
                  alignSelf: 'flex-start',
                  marginTop: 13,
                  minWidth: 16,
                  transition: 'background 250ms',
                }}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

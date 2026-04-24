interface StatProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  glow?: boolean;
}

export default function Stat({
  label,
  value,
  sub,
  color = 'var(--gold)',
  glow = false,
}: StatProps) {
  return (
    <div
      style={{
        background: 'var(--surface2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: 'var(--text3)',
        }}
      >
        {label}
      </span>

      <span
        style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 700,
          fontSize: 22,
          color,
          letterSpacing: '-0.02em',
          lineHeight: 1,
          textShadow: glow ? `0 0 16px ${color}` : undefined,
        }}
      >
        {value}
      </span>

      {sub && (
        <span
          style={{
            fontSize: 11,
            color: 'var(--text3)',
            marginTop: 1,
          }}
        >
          {sub}
        </span>
      )}
    </div>
  );
}

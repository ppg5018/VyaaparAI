interface LogoProps {
  size?: number;
}

export default function Logo({ size = 32 }: LogoProps) {
  const markW = Math.round(size * 1.5);
  const markH = size;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {/* Gold mark: lightning bolt + VA */}
      <div
        style={{
          width: markW,
          height: markH,
          background: 'var(--gold)',
          borderRadius: Math.round(size * 0.18),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: Math.round(size * 0.1),
          flexShrink: 0,
        }}
      >
        <svg
          width={Math.round(size * 0.3)}
          height={Math.round(size * 0.48)}
          viewBox="0 0 10 16"
          fill="black"
        >
          <path d="M7 0L0 9h4.5L3 16 10 7H5.5L7 0z" />
        </svg>
        <span
          style={{
            fontFamily: 'var(--font-space-grotesk), sans-serif',
            fontWeight: 700,
            fontSize: Math.round(size * 0.44),
            color: '#000',
            letterSpacing: '-0.03em',
            lineHeight: 1,
          }}
        >
          RF
        </span>
      </div>

      {/* Wordmark + tagline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span
          style={{
            fontFamily: 'var(--font-space-grotesk), sans-serif',
            fontWeight: 700,
            fontSize: Math.round(size * 0.56),
            color: 'var(--text)',
            letterSpacing: '-0.03em',
            lineHeight: 1,
          }}
        >
          Refloat
        </span>
        <span
          style={{
            fontSize: Math.round(size * 0.24),
            color: 'var(--text3)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            lineHeight: 1,
          }}
        >
          Business Health Monitor
        </span>
      </div>
    </div>
  );
}

import { Aurora, Logo, ThemeToggle } from '@/components/ui';

const FEATURES = [
  'Real-time Google Reviews & competitor tracking',
  'POS sales signals — Petpooja, Tally, BharatPe',
  'AI insights delivered to WhatsApp every Monday',
];

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
      }}
    >
      {/* ── LEFT PANEL ─────────────────────────────── */}
      <div
        className="auth-left"
        style={{
          background: 'var(--bg2)',
          flexDirection: 'column',
          padding: '40px 48px',
          borderRight: '1px solid var(--border)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle grain texture overlay */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'radial-gradient(ellipse 80% 60% at 50% 0%, rgba(245,166,35,0.06) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        {/* Logo */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <Logo size={28} />
        </div>

        {/* Hero copy */}
        <div style={{ marginTop: 64, position: 'relative', zIndex: 1 }}>
          <h1
            style={{
              fontFamily: 'var(--font-space-grotesk), sans-serif',
              fontWeight: 700,
              fontSize: 28,
              lineHeight: 1.25,
              letterSpacing: '-0.03em',
              color: 'var(--text)',
              margin: 0,
              marginBottom: 10,
            }}
          >
            Know your business health<br />
            <span style={{ color: 'var(--gold)' }}>before your customers do.</span>
          </h1>
          <p
            style={{
              fontSize: 14,
              color: 'var(--text2)',
              margin: 0,
              lineHeight: 1.6,
            }}
          >
            Refloat turns raw reviews, sales data, and competitor signals
            into a single health score — every week.
          </p>
        </div>

        {/* Feature bullets */}
        <div
          style={{
            marginTop: 36,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            position: 'relative',
            zIndex: 1,
          }}
        >
          {FEATURES.map((f) => (
            <div key={f} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: 'var(--gold)',
                  flexShrink: 0,
                  marginTop: 5,
                }}
              />
              <span style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.5 }}>
                {f}
              </span>
            </div>
          ))}
        </div>

        {/* Score preview card */}
        <div
          style={{
            marginTop: 'auto',
            paddingTop: 48,
            position: 'relative',
            zIndex: 1,
          }}
        >
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border2)',
              borderRadius: 'var(--r2)',
              padding: '20px 24px',
              backdropFilter: 'blur(8px)',
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--text3)',
                display: 'block',
                marginBottom: 12,
              }}
            >
              Business Health Score
            </span>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, marginBottom: 8 }}>
              <span
                style={{
                  fontFamily: 'var(--font-space-grotesk), sans-serif',
                  fontWeight: 700,
                  fontSize: 52,
                  lineHeight: 1,
                  letterSpacing: '-0.04em',
                  color: 'var(--emerald)',
                  textShadow: '0 0 24px var(--emerald)',
                }}
              >
                74
              </span>
              <span
                style={{
                  fontSize: 14,
                  color: 'var(--text3)',
                  marginBottom: 6,
                }}
              >
                /100
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
                color: 'var(--text2)',
              }}
            >
              <span style={{ color: 'var(--emerald)', fontSize: 8 }}>●</span>
              Healthy · Score updated Apr 21
            </div>

            {/* Mini score bars */}
            <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                { label: 'Reviews',    pct: 82, color: 'var(--emerald)' },
                { label: 'Competitor', pct: 61, color: 'var(--yellow)'  },
                { label: 'POS Sales',  pct: 74, color: 'var(--violet)'  },
              ].map(({ label, pct, color }) => (
                <div key={label}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: 3,
                      fontSize: 10,
                      color: 'var(--text3)',
                    }}
                  >
                    <span>{label}</span>
                    <span
                      style={{
                        fontFamily: 'var(--font-space-mono), monospace',
                        color: 'var(--text2)',
                      }}
                    >
                      {pct}
                    </span>
                  </div>
                  <div
                    style={{
                      height: 3,
                      background: 'rgba(255,255,255,0.06)',
                      borderRadius: 999,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${pct}%`,
                        height: '100%',
                        background: color,
                        borderRadius: 999,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Claude badge */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              marginTop: 14,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 20,
              padding: '4px 12px',
              fontSize: 11,
              color: 'var(--text3)',
            }}
          >
            ⚡ Powered by Claude
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL ────────────────────────────── */}
      <div
        style={{
          flex: 1,
          background: 'var(--bg)',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 24px',
          minHeight: '100vh',
        }}
      >
        <Aurora />

        {/* Theme toggle */}
        <div
          style={{
            position: 'absolute',
            top: 24,
            right: 24,
            zIndex: 10,
          }}
        >
          <ThemeToggle />
        </div>

        {/* Page content */}
        <div
          style={{
            width: '100%',
            maxWidth: 400,
            position: 'relative',
            zIndex: 1,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

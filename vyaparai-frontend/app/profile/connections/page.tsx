'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { useBusinessId } from '@/lib/business-context';
import { generateReport, type HealthReport } from '@/lib/api';
import { Logo, ThemeToggle } from '@/components/ui';

// ─── Types ─────────────────────────────────────────────────────────────────────
type Status = 'connected' | 'manual' | 'coming_soon' | 'inactive';

interface Connection {
  id:          string;
  icon:        string;
  name:        string;
  description: string;
  status:      Status;
  detail?:     string;
  actionLabel: string;
  onClick?:    () => void;
}

// ─── Status pill ───────────────────────────────────────────────────────────────
const STATUS_STYLE: Record<Status, { color: string; bg: string; border: string; label: string }> = {
  connected:   { color: 'var(--emerald)', bg: 'var(--emerald-dim)', border: 'rgba(16,217,160,0.35)', label: 'Connected'   },
  manual:      { color: 'var(--gold)',    bg: 'var(--gold-dim)',    border: 'rgba(245,166,35,0.35)', label: 'Manual CSV'  },
  coming_soon: { color: 'var(--text3)',   bg: 'var(--surface2)',    border: 'var(--border2)',         label: 'Coming soon' },
  inactive:    { color: 'var(--text3)',   bg: 'var(--surface2)',    border: 'var(--border2)',         label: 'Off'         },
};

function StatusPill({ status }: { status: Status }) {
  const s = STATUS_STYLE[status];
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
      color: s.color, background: s.bg, border: `1px solid ${s.border}`,
      borderRadius: 999, padding: '3px 10px', display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0,
    }}>
      {status === 'connected' && (
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: s.color, animation: 'pulse 2s ease-in-out infinite' }} />
      )}
      {s.label}
    </span>
  );
}

// ─── Connection card ───────────────────────────────────────────────────────────
function Card({ c }: { c: Connection }) {
  const enabled = c.status === 'connected' || c.status === 'manual';
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--r2)', padding: '18px 20px',
      display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <div style={{
        width: 44, height: 44, flexShrink: 0,
        borderRadius: 12, background: 'var(--surface2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 22, opacity: enabled ? 1 : 0.55,
      }}>
        {c.icon}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 3, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 15, color: 'var(--text)' }}>
            {c.name}
          </span>
          <StatusPill status={c.status} />
        </div>
        <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0, lineHeight: 1.5 }}>
          {c.description}
          {c.detail && <span style={{ color: 'var(--text2)' }}> · {c.detail}</span>}
        </p>
      </div>

      <button
        onClick={c.onClick}
        disabled={c.status === 'coming_soon'}
        style={{
          flexShrink: 0, padding: '8px 14px',
          background: enabled ? 'var(--surface2)' : 'transparent',
          border: `1px solid ${enabled ? 'var(--border2)' : 'var(--border)'}`,
          borderRadius: 'var(--r)',
          color: c.status === 'coming_soon' ? 'var(--text3)' : 'var(--text2)',
          fontFamily: 'inherit', fontSize: 12, fontWeight: 500,
          cursor: c.status === 'coming_soon' ? 'not-allowed' : 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        {c.actionLabel}
      </button>
    </div>
  );
}

// ─── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, subtitle, items }: { title: string; subtitle: string; items: Connection[] }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h3 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 14, color: 'var(--text)', margin: '0 0 3px', letterSpacing: '-0.01em' }}>
          {title}
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0, lineHeight: 1.5 }}>{subtitle}</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((c) => <Card key={c.id} c={c} />)}
      </div>
    </section>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────
export default function ConnectionsPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { businessId, bizLoading } = useBusinessId();

  const [report, setReport] = useState<HealthReport | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchReport = useCallback(async (id: string) => {
    try { setReport(await generateReport(id)); }
    catch { /* non-fatal — connections page can still render */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (authLoading || bizLoading) return;
    if (!user) { router.push('/login'); return; }
    if (!businessId) { router.push('/onboard/pos'); return; }
    fetchReport(businessId);
  }, [authLoading, bizLoading, user, businessId, fetchReport, router]);

  // ─── Derive integration statuses ─────────────────────────────────────────────
  const googleConnected = !!report && report.total_reviews > 0;
  const googleSync = report?.generated_at
    ? new Date(report.generated_at).toLocaleString('en-IN', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : null;

  const reviewsAndListings: Connection[] = [
    {
      id: 'google',
      icon: '🌐',
      name: 'Google Reviews & Maps',
      description: 'Reviews, ratings, and competitor data via Apify (cached 7 days).',
      status: googleConnected ? 'connected' : 'inactive',
      detail: googleConnected
        ? `${report?.total_reviews?.toLocaleString() ?? 0} total reviews · synced ${googleSync ?? '—'}`
        : 'Add a Google Place ID during onboarding to enable.',
      actionLabel: googleConnected ? 'Manage' : 'Re-onboard',
      onClick: () => router.push('/onboard/business?from=connections'),
    },
    {
      id: 'zomato',
      icon: '🍔',
      name: 'Zomato',
      description: 'Restaurant reviews from your Zomato Partner Hub. Manual CSV export upload.',
      status: 'coming_soon',
      detail: 'No public OAuth — CSV flow coming soon',
      actionLabel: 'Notify me',
    },
    {
      id: 'swiggy',
      icon: '🛵',
      name: 'Swiggy',
      description: 'Reviews from your Swiggy Partner Hub via weekly performance email parsing.',
      status: 'coming_soon',
      detail: 'No public OAuth — email-forward flow coming soon',
      actionLabel: 'Notify me',
    },
  ];

  const posAndPayments: Connection[] = [
    {
      id: 'petpooja',
      icon: '🍽️',
      name: 'Petpooja',
      description: 'Upload daily/weekly POS exports to get product mix, AOV, and revenue trends.',
      status: 'manual',
      detail: 'CSV upload via /onboard/pos',
      actionLabel: 'Upload CSV',
      onClick: () => router.push('/onboard/pos'),
    },
    {
      id: 'razorpay',
      icon: '💳',
      name: 'Razorpay',
      description: 'Payment trends, refund rate, and settlement health from your Razorpay account.',
      status: 'coming_soon',
      detail: 'OAuth integration on roadmap',
      actionLabel: 'Notify me',
    },
    {
      id: 'bharatpe',
      icon: '📲',
      name: 'BharatPe',
      description: 'UPI transaction signals — daily volume, repeat customers, peak hours.',
      status: 'coming_soon',
      detail: 'Partner API coming soon',
      actionLabel: 'Notify me',
    },
    {
      id: 'paytm',
      icon: '💰',
      name: 'Paytm for Business',
      description: 'Track Paytm QR + soundbox transactions alongside your other payment rails.',
      status: 'coming_soon',
      actionLabel: 'Notify me',
    },
  ];

  const notifications: Connection[] = [
    {
      id: 'email',
      icon: '📧',
      name: 'Email',
      description: 'Weekly health reports and score-drop alerts to your inbox.',
      status: 'inactive',
      detail: user?.email ? `Sends to ${user.email}` : undefined,
      actionLabel: 'Enable',
    },
    {
      id: 'whatsapp',
      icon: '💬',
      name: 'WhatsApp',
      description: 'A "your report is ready" message links you to the dashboard. Notification only — not a chatbot.',
      status: 'coming_soon',
      detail: 'Awaiting Meta WABA approval',
      actionLabel: 'Notify me',
    },
    {
      id: 'sms',
      icon: '📱',
      name: 'SMS',
      description: 'Score-drop alerts via SMS. Slower fallback for users who don\'t check email.',
      status: 'coming_soon',
      actionLabel: 'Notify me',
    },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>

      {/* Nav */}
      <nav style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--nav-bg)', backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)', borderBottom: '1px solid var(--border)', height: 60, display: 'flex', alignItems: 'center', padding: '0 20px', gap: 12 }}>
        <Logo size={26} />
        <div style={{ flex: 1 }} />
        <Link href="/dashboard" style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 12px', borderRadius: 8,
          fontSize: 13, color: 'var(--text2)', textDecoration: 'none',
          border: '1px solid var(--border)', background: 'transparent',
        }}>
          <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
            <line x1={19} y1={12} x2={5} y2={12} /><polyline points="12 19 5 12 12 5" />
          </svg>
          Back to dashboard
        </Link>
        <ThemeToggle />
      </nav>

      {/* Page */}
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px 80px', display: 'flex', flexDirection: 'column', gap: 32 }}>

        {/* Header */}
        <div>
          <h1 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 28, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 6px' }}>
            Connections
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text3)', margin: 0, lineHeight: 1.6 }}>
            Manage how VyaparAI pulls data from your business systems and how you get notified.
          </p>
        </div>

        {/* Summary banner */}
        <div style={{
          background: 'linear-gradient(135deg, rgba(245,166,35,0.08), rgba(139,111,255,0.08))',
          border: '1px solid var(--border2)', borderRadius: 'var(--r2)',
          padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--gold)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="black" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
              <polyline points="2.5,7 5.5,10 11.5,3.5" />
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, fontWeight: 500 }}>
              {loading ? 'Checking your connections…' : (
                <>
                  <strong>{[googleConnected, true].filter(Boolean).length}</strong> active · <strong>{8}</strong> coming soon
                </>
              )}
            </p>
            <span style={{ fontSize: 12, color: 'var(--text3)' }}>
              The more sources you connect, the more accurate your insights become.
            </span>
          </div>
        </div>

        <Section
          title="Reviews & Listings"
          subtitle="Where your customers leave feedback"
          items={reviewsAndListings}
        />

        <Section
          title="POS & Payments"
          subtitle="Sales, transaction, and inventory data"
          items={posAndPayments}
        />

        <Section
          title="Notifications"
          subtitle="How VyaparAI reaches you outside the app"
          items={notifications}
        />

        <p style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center', margin: 0, lineHeight: 1.5 }}>
          Want a connection that&apos;s not here?{' '}
          <a href="mailto:hello@vyaparai.app?subject=Integration request" style={{ color: 'var(--gold)', textDecoration: 'none' }}>
            Tell us what you use →
          </a>
        </p>
      </div>
    </div>
  );
}

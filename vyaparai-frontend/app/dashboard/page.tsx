'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  generateReport, getHistory, getActions, logAction, deleteAction,
  searchPlaces, addCompetitor, removeCompetitor, getPosDashboard,
  type ActionEntry, type Band, type HealthReport, type HistoryEntry,
  type PlaceSuggestion, type PosDashboard,
} from '@/lib/api';
import { useBusinessId } from '@/lib/business-context';
import { useAuth } from '@/lib/auth-context';
import { useViewport } from '@/lib/use-viewport';
import { Bars, Gauge, Logo, Skeleton, Stat, ThemeToggle } from '@/components/ui';

// ─── POS display helpers ───────────────────────────────────────────────────────
const CAT_COLORS = ['var(--gold)', 'var(--violet)', 'var(--emerald)', 'var(--red)', 'var(--yellow)', '#7dd3fc', '#f472b6', '#94a3b8'];

function formatTrend(pct: number | null): string {
  if (pct == null) return '—';
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

function formatAov(dir: string | null): string {
  if (!dir) return '—';
  if (dir === 'rising')  return '↑ Up';
  if (dir === 'falling') return '↓ Down';
  return '→ Stable';
}

function aovColor(dir: string | null): string {
  if (dir === 'rising')  return 'var(--emerald)';
  if (dir === 'falling') return 'var(--red)';
  return 'var(--violet)';
}

function trendColor(pct: number | null): string {
  if (pct == null) return 'var(--text3)';
  if (pct > 0)  return 'var(--emerald)';
  if (pct < 0)  return 'var(--red)';
  return 'var(--text2)';
}

// ─── Types ─────────────────────────────────────────────────────────────────────
type Tab         = 'overview' | 'insights' | 'competitors' | 'pos' | 'history' | 'notes';
type DisplayBand = 'green' | 'yellow' | 'red';

interface ActionsCtx {
  actions: ActionEntry[];
  onLog: (kind: ActionEntry['kind'], targetText: string, note?: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview',    label: 'Overview'    },
  { id: 'insights',    label: 'Insights'    },
  { id: 'competitors', label: 'Competitors' },
  { id: 'pos',         label: 'POS'         },
  { id: 'history',     label: 'History'     },
  { id: 'notes',       label: 'Notes'       },
];

// ─── Helpers ───────────────────────────────────────────────────────────────────
function mapBand(band: Band): DisplayBand {
  if (band === 'healthy') return 'green';
  if (band === 'watch')   return 'yellow';
  return 'red';
}

function scoreToBand(score: number): DisplayBand {
  if (score >= 70) return 'green';
  if (score >= 45) return 'yellow';
  return 'red';
}

function toWeekLabel(isoDate: string): string {
  const d = new Date(isoDate);
  const month = d.toLocaleString('en-US', { month: 'short' });
  return `${month} W${Math.ceil(d.getDate() / 7)}`;
}

function userDisplayName(user: { email?: string; user_metadata?: Record<string, unknown> } | null): string {
  if (!user) return '';
  const meta = user.user_metadata ?? {};
  const candidates = [
    meta.full_name,
    meta.name,
    meta.given_name,
    user.email?.split('@')[0],
  ];
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim();
  }
  return '';
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (!then) return '';
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (sec < 60)    return 'just now';
  if (sec < 3600)  return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

// ─── Shared styles ─────────────────────────────────────────────────────────────
const CARD: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r2)',
  padding: '20px',
  position: 'relative',
  overflow: 'hidden',
};
const SEC: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, letterSpacing: '0.08em',
  textTransform: 'uppercase', color: 'var(--text3)',
  margin: '0 0 14px', display: 'block',
};
const GHOST_BTN: React.CSSProperties = {
  background: 'transparent', border: '1px solid var(--border2)', borderRadius: 6,
  padding: '5px 10px', fontSize: 11, color: 'var(--text2)', cursor: 'pointer', fontFamily: 'inherit',
};

const BAND_COLOR: Record<DisplayBand, string> = { green: 'var(--emerald)', yellow: 'var(--yellow)', red: 'var(--red)' };
const BAND_DIM:   Record<DisplayBand, string> = { green: 'var(--emerald-dim)', yellow: 'var(--yellow-dim)', red: 'var(--red-dim)' };
const BAND_LABEL: Record<DisplayBand, string> = { green: 'Healthy', yellow: 'Needs Attention', red: 'Critical' };

const INSIGHT_COLORS = ['var(--violet)', 'var(--gold)',     'var(--emerald)'];
const INSIGHT_DIMS   = ['var(--violet-dim)', 'var(--gold-dim)', 'var(--emerald-dim)'];

// ─── Micro components ──────────────────────────────────────────────────────────
function Stars({ n }: { n: number }) {
  return (
    <span style={{ display: 'flex', gap: 1 }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} style={{ fontSize: 11, color: i <= n ? 'var(--gold)' : 'var(--text3)' }}>★</span>
      ))}
    </span>
  );
}

function Spin({ size = 14, dark = false }: { size?: number; dark?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite', flexShrink: 0 }}>
      <circle cx={8} cy={8} r={6} stroke={dark ? 'rgba(0,0,0,0.2)' : 'rgba(255,255,255,0.2)'} strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke={dark ? '#000' : '#fff'} strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

function Toast({ onClose }: { onClose: () => void }) {
  useEffect(() => { const t = setTimeout(onClose, 3000); return () => clearTimeout(t); }, [onClose]);
  return (
    <div style={{
      position: 'fixed', top: 76, right: 24, zIndex: 1000,
      background: 'var(--emerald-dim)', border: '1px solid var(--emerald)',
      borderRadius: 'var(--r)', padding: '10px 16px',
      display: 'flex', alignItems: 'center', gap: 8,
      fontSize: 13, fontWeight: 500, color: 'var(--emerald)',
      animation: 'fadeUp 0.3s ease both', boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
    }}>
      <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <polyline points="2,7 5.5,10.5 12,3" />
      </svg>
      Report refreshed!
    </div>
  );
}

// One row inside SuggestionsBanner. Mark Done logs to the actions table; the
// outer SuggestionsBanner re-filters on every render so the row disappears
// once a matching action_log entry exists — both immediately (state update)
// and after refresh (server-fetched ctx.actions).
function SuggestionRow({
  text, kind, ctx,
}: {
  text: string;
  kind: ActionEntry['kind'];
  ctx: ActionsCtx;
}) {
  const [busy, setBusy] = useState(false);
  const { isMobile } = useViewport();

  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await ctx.onLog(kind, text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(245,166,35,0.1), rgba(139,111,255,0.1))',
      border: '1px solid var(--border2)',
      borderRadius: 'var(--r2)',
      padding: isMobile ? '14px 16px' : '18px 20px',
      display: 'flex',
      flexDirection: isMobile ? 'column' : 'row',
      alignItems: isMobile ? 'stretch' : 'flex-start',
      gap: isMobile ? 12 : 14,
      transition: 'background 250ms, border-color 250ms',
    }}>
      <div style={{ width: 36, height: 36, background: 'var(--gold)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width={14} height={18} viewBox="0 0 10 16" fill="black"><path d="M7 0L0 9h4.5L3 16 10 7H5.5L7 0z" /></svg>
      </div>
      <div style={{ flex: 1 }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text3)', display: 'block', marginBottom: 5 }}>
          {kind === 'weekly_action_done' ? "This Week's Action" : 'Suggested Action'}
        </span>
        <p style={{ fontSize: 13, color: 'var(--text2)', margin: 0, lineHeight: 1.65 }}>{text}</p>
      </div>
      <button
        onClick={onClick}
        disabled={busy}
        style={{
          flexShrink: 0, padding: '8px 14px',
          background: 'var(--gold)',
          border: 'none',
          borderRadius: 8,
          color: '#000',
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 600, fontSize: 12, cursor: busy ? 'wait' : 'pointer',
          whiteSpace: 'nowrap', opacity: busy ? 0.6 : 1,
          transition: 'background 200ms, opacity 150ms',
        }}
      >
        {busy ? '…' : 'Mark Done'}
      </button>
    </div>
  );
}

function SuggestionsBanner({
  action, insights, ctx,
}: {
  action: string;
  insights: readonly string[];
  ctx: ActionsCtx;
}) {
  // Combine the headline weekly action + all insights into a single suggestion list.
  // Hidden once an action_log entry exists with matching target_text — both
  // 'weekly_action_done' and 'insight_actioned' kinds count as "done".
  const all: { text: string; kind: ActionEntry['kind'] }[] = [
    ...(action ? [{ text: action, kind: 'weekly_action_done' as const }] : []),
    ...insights.map((text) => ({ text, kind: 'insight_actioned' as const })),
  ];

  const seen = new Set<string>();
  // Order = priority: report.action first (Claude's headline), then insights in
  // the order Claude returned them. Cap to 2 so the user sees the top items —
  // when one is marked done it falls out of the actions filter and the next
  // pending suggestion slides up automatically on the next render.
  const pending = all.filter((item) => {
    if (seen.has(item.text)) return false;
    seen.add(item.text);
    return !ctx.actions.some(
      (a) =>
        a.target_text === item.text &&
        (a.kind === 'weekly_action_done' || a.kind === 'insight_actioned'),
    );
  });
  const visible = pending.slice(0, 2);

  if (visible.length === 0) {
    return (
      <div style={{
        background: 'linear-gradient(135deg, rgba(16,217,160,0.10), rgba(16,217,160,0.05))',
        border: '1px solid rgba(16,217,160,0.3)',
        borderRadius: 'var(--r2)',
        padding: '18px 20px',
        marginTop: 16,
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{ width: 36, height: 36, background: 'var(--emerald)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <svg width={16} height={16} viewBox="0 0 16 16" fill="none" stroke="black" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3,8 7,12 13,4" />
          </svg>
        </div>
        <div>
          <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--emerald)', display: 'block', marginBottom: 5 }}>All Caught Up</span>
          <p style={{ fontSize: 13, color: 'var(--text2)', margin: 0, lineHeight: 1.65 }}>You've marked every suggestion done. Undo any from the Notes tab if you change your mind.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
      {visible.map((item) => (
        <SuggestionRow key={`${item.kind}:${item.text}`} text={item.text} kind={item.kind} ctx={ctx} />
      ))}
    </div>
  );
}

// ─── Loading screen ────────────────────────────────────────────────────────────
function DashboardLoader() {
  const stages = [
    'Fetching Google reviews and ratings',
    'Computing your health score',
    'Generating AI-powered insights',
    'Analyzing top competitors',
    'Polishing the final report',
  ];
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setStageIdx((i) => (i < stages.length - 1 ? i + 1 : i));
    }, 2800);
    return () => clearInterval(id);
  }, [stages.length]);

  const Check = () => (
    <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
      <circle cx={7} cy={7} r={6} fill="var(--emerald-dim)" stroke="var(--emerald)" strokeWidth={1} />
      <polyline points="3.5,7 6,9.5 10.5,4.5" stroke="var(--emerald)" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );

  const Dot = () => (
    <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
      <circle cx={7} cy={7} r={5.5} stroke="var(--border2)" strokeWidth={1} />
    </svg>
  );

  const Pending = () => (
    <svg width={14} height={14} viewBox="0 0 16 16" fill="none" style={{ animation: 'spin 0.85s linear infinite' }}>
      <circle cx={8} cy={8} r={6} stroke="var(--border2)" strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="var(--gold)" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );

  return (
    <div style={{
      minHeight: 'calc(100vh - 200px)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 32, padding: '40px 20px', position: 'relative',
    }}>
      {/* Subtle gradient backdrop */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 60% 50% at 50% 30%, rgba(245,166,35,0.08), transparent 60%)',
      }} />

      {/* Concentric rotating rings */}
      <div style={{ position: 'relative', width: 96, height: 96, zIndex: 1 }}>
        <div style={{
          position: 'absolute', inset: 12, borderRadius: '50%',
          background: 'radial-gradient(circle, var(--gold-dim), transparent 70%)',
          animation: 'pulse 2.4s ease-in-out infinite',
        }} />
        <svg width={96} height={96} viewBox="0 0 96 96" style={{ position: 'absolute', inset: 0 }}>
          <circle cx={48} cy={48} r={40} fill="none" stroke="var(--gold)"    strokeWidth={3}
            strokeDasharray="60 220" strokeLinecap="round"
            style={{ transformOrigin: 'center', animation: 'spin 1.6s linear infinite' }} />
          <circle cx={48} cy={48} r={30} fill="none" stroke="var(--violet)"  strokeWidth={2.5}
            strokeDasharray="45 160" strokeLinecap="round"
            style={{ transformOrigin: 'center', animation: 'spin 2.4s linear infinite reverse' }} />
          <circle cx={48} cy={48} r={20} fill="none" stroke="var(--emerald)" strokeWidth={2}
            strokeDasharray="25 100" strokeLinecap="round"
            style={{ transformOrigin: 'center', animation: 'spin 1.1s linear infinite' }} />
          <circle cx={48} cy={48} r={4} fill="var(--gold)" />
        </svg>
      </div>

      <div style={{ textAlign: 'center', zIndex: 1 }}>
        <h2 style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700,
          fontSize: 22, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 6px',
        }}>
          Building your business report
        </h2>
        <p style={{ fontSize: 13, color: 'var(--text3)', margin: 0 }}>
          This usually takes 10–15 seconds
        </p>
      </div>

      {/* Stage list */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 12,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--r2)', padding: '18px 22px', minWidth: 320, zIndex: 1,
      }}>
        {stages.map((s, i) => {
          const status = i < stageIdx ? 'done' : i === stageIdx ? 'active' : 'pending';
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 12,
              opacity: status === 'pending' ? 0.4 : 1,
              transition: 'opacity 400ms',
            }}>
              <span style={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                {status === 'done' ? <Check /> : status === 'active' ? <Pending /> : <Dot />}
              </span>
              <span style={{
                fontSize: 13,
                color: status === 'active' ? 'var(--text)' : 'var(--text2)',
                fontWeight: status === 'active' ? 500 : 400,
              }}>
                {s}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Full-page error ───────────────────────────────────────────────────────────
function ErrorPage({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div style={{ padding: '60px 24px', display: 'flex', justifyContent: 'center' }}>
      <div style={{
        ...CARD, maxWidth: 480, width: '100%',
        borderColor: 'var(--red)', background: 'var(--red-dim)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, textAlign: 'center',
      }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--red-dim)', border: '1.5px solid var(--red)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={18} height={18} viewBox="0 0 18 18" fill="none" stroke="var(--red)" strokeWidth={2} strokeLinecap="round">
            <circle cx={9} cy={9} r={8} />
            <line x1={9} y1={5} x2={9} y2={9.5} />
            <line x1={9} y1={12} x2={9} y2={13} />
          </svg>
        </div>
        <div>
          <p style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 16, color: 'var(--text)', margin: '0 0 6px' }}>Failed to load report</p>
          <p style={{ fontSize: 13, color: 'var(--text2)', margin: 0, lineHeight: 1.6 }}>{message}</p>
        </div>
        <button onClick={onRetry} style={{ padding: '9px 20px', background: 'var(--gold)', border: 'none', borderRadius: 'var(--r)', color: '#000', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
          Try again
        </button>
      </div>
    </div>
  );
}

// ─── TAB: Overview ─────────────────────────────────────────────────────────────
type ReviewFilter = 'all' | 'positive' | 'negative';

function OverviewTab({ report, ctx }: { report: HealthReport; ctx: ActionsCtx }) {
  const band = mapBand(report.band);
  const { isMobile, isTablet } = useViewport();
  const overviewCols = isMobile ? '1fr'
    : isTablet ? '1fr'
    : '280px minmax(0, 1fr) minmax(0, 1fr)';
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('all');

  const allReviews = report.reviews.filter((r) => r.text.trim());
  const posCount   = allReviews.filter((r) => r.rating >= 4).length;
  const negCount   = allReviews.filter((r) => r.rating <= 3).length;
  const visible    = reviewFilter === 'positive'
    ? allReviews.filter((r) => r.rating >= 4)
    : reviewFilter === 'negative'
      ? allReviews.filter((r) => r.rating <= 3)
      : allReviews;

  const FilterBtn = ({ id, label, count, color }: { id: ReviewFilter; label: string; count: number; color: string }) => {
    const active = reviewFilter === id;
    return (
      <button
        onClick={() => setReviewFilter(id)}
        style={{
          flex: 1,
          padding: '5px 8px',
          borderRadius: 6,
          border: `1px solid ${active ? color : 'var(--border2)'}`,
          background: active ? `${color}22` : 'transparent',
          color: active ? color : 'var(--text2)',
          fontSize: 11,
          fontWeight: 600,
          cursor: 'pointer',
          fontFamily: 'inherit',
          letterSpacing: '0.02em',
          transition: 'background 150ms, color 150ms, border-color 150ms',
        }}
      >
        {label} <span style={{ opacity: 0.7, fontWeight: 500 }}>· {count}</span>
      </button>
    );
  };
  const subScoreRow = (label: string, weight: number, value: number, color: string) => (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ fontSize: 13, color: 'var(--text2)', whiteSpace: 'nowrap' }}>
        {label} <span style={{ color: 'var(--text3)' }}>({weight}%)</span>
      </span>
      <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 18, color, lineHeight: 1 }}>
        {value}
      </span>
    </div>
  );

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: overviewCols, gap: 16, alignItems: 'stretch' }}>

        {/* Col 1 — Health Score */}
        <div style={{ ...CARD, padding: '22px 20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'radial-gradient(ellipse 120% 60% at 50% 0%, rgba(16,217,160,0.07), transparent 60%)', pointerEvents: 'none' }} />
          <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', gap: 22, flex: 1 }}>
            <span style={{ ...SEC, textAlign: 'center', margin: 0 }}>Health Score</span>
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
              <Gauge score={report.final_score} band={band} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 'auto', paddingTop: 6 }}>
              {subScoreRow('Review Score',     40, report.sub_scores.review_score,     'var(--violet)')}
              {subScoreRow('Competitor Score', 25, report.sub_scores.competitor_score, 'var(--gold)')}
              {subScoreRow('POS Score',        35, report.sub_scores.pos_score,        'var(--emerald)')}
            </div>
          </div>
        </div>

        {/* Col 2 — Google Presence */}
        <div style={{ ...CARD, display: 'flex', flexDirection: 'column' }}>
          <span style={SEC}>Google Presence</span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
            <Stat label="Rating"  value={`${report.google_rating}★`} sub={`Area avg ~${Math.max(0, report.google_rating - 0.2).toFixed(1)}★`}  color="var(--gold)"   glow />
            <Stat label="Reviews" value={String(report.total_reviews)} sub="+14 this month" color="var(--violet)" />
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <FilterBtn id="all"      label="All"      count={allReviews.length} color="var(--text2)" />
            <FilterBtn id="positive" label="Positive" count={posCount}          color="var(--emerald)" />
            <FilterBtn id="negative" label="Negative" count={negCount}          color="var(--red)" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, maxHeight: 280, overflowY: 'auto' }}>
            {allReviews.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No reviews available — add a Google Place ID to see real reviews.</p>
            ) : visible.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0, textAlign: 'center', padding: '12px 0' }}>
                No {reviewFilter} reviews yet.
              </p>
            ) : visible.map((r, i) => (
              <div key={i} style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 'var(--r)', padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12, minHeight: 44, flexShrink: 0 }}>
                <span style={{ flexShrink: 0 }}><Stars n={r.rating} /></span>
                <p style={{ fontSize: 12, color: 'var(--text2)', margin: 0, lineHeight: 1.5, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{r.text}</p>
              </div>
            ))}
          </div>
          {report.total_reviews > allReviews.length && (
            <p style={{ fontSize: 10, color: 'var(--text3)', margin: '8px 0 0', lineHeight: 1.4, fontStyle: 'italic' }}>
              Showing {allReviews.length} of {report.total_reviews.toLocaleString()} total reviews · Google&apos;s Places API caps responses at 5 per business.
            </p>
          )}
        </div>

        {/* Col 3 — POS Signals */}
        <div style={{ ...CARD, display: 'flex', flexDirection: 'column' }}>
          <span style={SEC}>POS Signals · 30 Days</span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 18 }}>
            <Stat
              label="Revenue Trend"
              value={formatTrend(report.pos_signals.revenue_trend_pct)}
              sub="vs prior month"
              color={trendColor(report.pos_signals.revenue_trend_pct)}
              glow
            />
            <Stat
              label="Top Product"
              value={report.pos_signals.top_product ?? '—'}
              sub={report.revenue_by_category[0] ? `${report.revenue_by_category[0].pct}% of revenue` : 'no POS data'}
              color="var(--gold)"
            />
            <Stat
              label="AOV Direction"
              value={formatAov(report.pos_signals.aov_direction)}
              sub="avg order value"
              color={aovColor(report.pos_signals.aov_direction)}
            />
            {report.pos_signals.slow_categories.length > 0 ? (
              <div style={{ background: 'var(--red-dim)', border: '1px solid rgba(255,95,95,0.25)', borderRadius: 'var(--r)', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4, justifyContent: 'center' }}>
                <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text3)' }}>Slow</span>
                <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 15, color: 'var(--red)', lineHeight: 1.25 }}>
                  {report.pos_signals.slow_categories.join(', ')}
                </span>
              </div>
            ) : (
              <Stat
                label="Repeat Rate"
                value={report.pos_signals.repeat_rate_pct != null ? `${report.pos_signals.repeat_rate_pct.toFixed(1)}%` : '—'}
                sub={report.pos_signals.repeat_rate_trend != null ? `${formatTrend(report.pos_signals.repeat_rate_trend)} vs prior` : 'returning customers'}
                color="var(--emerald)"
              />
            )}
          </div>
          <div style={{ marginTop: 'auto' }}>
            <span style={{ ...SEC, marginBottom: 8 }}>8-Week Revenue</span>
            {report.weekly_revenue.length > 0 ? (
              <Bars data={report.weekly_revenue} height={80} />
            ) : (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0, textAlign: 'center', padding: '24px 0' }}>
                Upload POS data to see revenue trends.
              </p>
            )}
          </div>
        </div>
      </div>

      <SuggestionsBanner action={report.action} insights={report.insights} ctx={ctx} />
    </div>
  );
}

// ─── Insight card (stateful) ───────────────────────────────────────────────────
function InsightCard({ text, idx, ctx }: { text: string; idx: number; ctx: ActionsCtx }) {
  const actionedEntry = ctx.actions.find((a) => a.kind === 'insight_actioned' && a.target_text === text);
  const savedEntry    = ctx.actions.find((a) => a.kind === 'insight_saved'    && a.target_text === text);
  const isActioned = !!actionedEntry;
  const isSaved    = !!savedEntry;

  const [busy, setBusy] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState('');

  const toggleActioned = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (isActioned && actionedEntry) await ctx.onDelete(actionedEntry.id);
      else                             await ctx.onLog('insight_actioned', text);
    } finally { setBusy(false); }
  };

  const saveNote = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await ctx.onLog('insight_saved', text, noteText.trim() || undefined);
      setNoteOpen(false);
      setNoteText('');
    } finally { setBusy(false); }
  };

  const removeSaved = async () => {
    if (busy || !savedEntry) return;
    setBusy(true);
    try { await ctx.onDelete(savedEntry.id); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ ...CARD, display: 'flex', gap: 14, alignItems: 'flex-start', opacity: isActioned ? 0.65 : 1, transition: 'opacity 200ms' }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', background: isActioned ? 'var(--emerald-dim)' : INSIGHT_DIMS[idx], border: `1.5px solid ${isActioned ? 'var(--emerald)' : INSIGHT_COLORS[idx]}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 12, color: isActioned ? 'var(--emerald)' : INSIGHT_COLORS[idx], flexShrink: 0, transition: 'background 200ms, border-color 200ms' }}>
        {isActioned ? (
          <svg width={12} height={12} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
            <polyline points="2,6 5,9 10,3" />
          </svg>
        ) : idx + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 13, color: 'var(--text)', margin: '0 0 12px', lineHeight: 1.65, textDecoration: isActioned ? 'line-through' : 'none' }}>{text}</p>

        {/* Saved note display */}
        {isSaved && savedEntry && (
          <div style={{ marginBottom: 12, padding: '8px 12px', background: 'var(--violet-dim)', border: '1px solid rgba(139,111,255,0.25)', borderRadius: 'var(--r)', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <svg width={12} height={12} viewBox="0 0 12 12" fill="none" stroke="var(--violet)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 2 }}>
              <path d="M9 1H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1z" /><line x1={4} y1={4} x2={8} y2={4} /><line x1={4} y1={6} x2={8} y2={6} />
            </svg>
            <div style={{ flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--violet)', display: 'block', marginBottom: 2 }}>Saved note</span>
              <p style={{ fontSize: 12, color: 'var(--text2)', margin: 0, lineHeight: 1.5, fontStyle: savedEntry.note ? 'normal' : 'italic' }}>
                {savedEntry.note || '(no note added)'}
              </p>
            </div>
            <button onClick={removeSaved} disabled={busy} style={{ ...GHOST_BTN, padding: '3px 8px', fontSize: 10, flexShrink: 0 }}>Remove</button>
          </div>
        )}

        {/* Inline note form */}
        {noteOpen && !isSaved && (
          <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Add a note (optional)…"
              autoFocus
              rows={2}
              style={{
                width: '100%', resize: 'vertical', padding: '8px 10px',
                background: 'var(--surface2)', border: '1px solid var(--border2)',
                borderRadius: 'var(--r)', fontSize: 13, fontFamily: 'inherit',
                color: 'var(--text)', outline: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={saveNote} disabled={busy} style={{ ...GHOST_BTN, background: 'var(--violet)', border: 'none', color: '#fff', fontWeight: 600 }}>
                {busy ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => { setNoteOpen(false); setNoteText(''); }} disabled={busy} style={GHOST_BTN}>Cancel</button>
            </div>
          </div>
        )}

        {/* Action buttons */}
        {!noteOpen && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={toggleActioned} disabled={busy} style={{ ...GHOST_BTN, ...(isActioned ? { background: 'var(--emerald-dim)', borderColor: 'var(--emerald)', color: 'var(--emerald)' } : {}) }}>
              {isActioned ? '✓ Actioned' : 'Mark Actioned'}
            </button>
            {!isSaved && (
              <button onClick={() => setNoteOpen(true)} disabled={busy} style={GHOST_BTN}>Save to Notes</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── TAB: Insights ─────────────────────────────────────────────────────────────
function InsightsTab({ report, ctx }: { report: HealthReport; ctx: ActionsCtx }) {
  const ca = report.competitor_analysis;
  const hasAnalysis = ca && (ca.themes.length > 0 || ca.opportunities.length > 0);
  const { isMobile } = useViewport();
  const insightsCols = isMobile ? '1fr' : 'minmax(0, 1fr) minmax(0, 1fr)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 3px' }}>
            AI-Generated Insights
          </h2>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            Powered by Claude · Generated {new Date(report.generated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ background: 'var(--violet-dim)', border: '1px solid var(--violet)', borderRadius: 999, padding: '3px 12px', fontSize: 11, fontWeight: 600, color: 'var(--violet)' }}>
            {report.insights.length} insights
          </div>
          {hasAnalysis && (
            <div style={{ background: 'var(--gold-dim)', border: '1px solid var(--gold)', borderRadius: 999, padding: '3px 12px', fontSize: 11, fontWeight: 600, color: 'var(--gold)' }}>
              {ca.analyzed_count} competitors analyzed
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: insightsCols, gap: 16, alignItems: 'start' }}>

        {/* Left — Insights for the user */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <span style={SEC}>Your Business</span>
          {report.insights.map((text, i) => (
            <InsightCard key={i} text={text} idx={i} ctx={ctx} />
          ))}
        </div>

        {/* Right — Competitor analysis */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <span style={SEC}>Competitor Analysis</span>

          {!hasAnalysis ? (
            <div style={CARD}>
              <p style={{ fontSize: 13, color: 'var(--text3)', margin: 0, lineHeight: 1.6 }}>
                {ca && ca.analyzed_count === 0
                  ? 'No higher-rated competitors found nearby — you\'re leading the local pack.'
                  : 'Competitor analysis unavailable for this report.'}
              </p>
            </div>
          ) : (
            <>
              {/* What competitors do well */}
              <div style={{ ...CARD, borderColor: 'rgba(245,166,35,0.25)' }}>
                <span style={{ ...SEC, color: 'var(--gold)', marginBottom: 12 }}>What Competitors Do Well</span>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {ca.themes.map((t, i) => (
                    <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13, color: 'var(--text)', lineHeight: 1.55 }}>
                      <span style={{ flexShrink: 0, marginTop: 4, width: 5, height: 5, borderRadius: '50%', background: 'var(--gold)' }} />
                      <span style={{ flex: 1, minWidth: 0 }}>{t}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Opportunities to close the gap */}
              <div style={{ ...CARD, borderColor: 'rgba(16,217,160,0.25)' }}>
                <span style={{ ...SEC, color: 'var(--emerald)', marginBottom: 12 }}>Opportunities for You</span>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {ca.opportunities.map((o, i) => (
                    <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13, color: 'var(--text)', lineHeight: 1.55 }}>
                      <span style={{ flexShrink: 0, marginTop: 2, fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 12, color: 'var(--emerald)', width: 16 }}>
                        {i + 1}.
                      </span>
                      <span style={{ flex: 1, minWidth: 0 }}>{o}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
      </div>

      <SuggestionsBanner action={report.action} insights={report.insights} ctx={ctx} />
    </div>
  );
}

// ─── TAB: Competitors ──────────────────────────────────────────────────────────
function CompetitorsTab({
  report,
  businessId,
  onAdded,
  onRemoved,
}: {
  report: HealthReport;
  businessId: string;
  onAdded: (c: HealthReport['competitors'][number]) => void;
  onRemoved: (placeId: string) => void;
}) {
  const myRating    = report.google_rating;
  const myReviews   = report.total_reviews;
  const competitors = report.competitors;
  // A real threat must (a) outrank you AND (b) have credible review volume —
  // a 4.6★ with 20 reviews vs your 1,297 isn't statistically meaningful.
  const isThreatFn = (c: { rating: number; review_count: number }) =>
    c.rating > myRating &&
    c.review_count >= 50 &&
    c.review_count >= myReviews * 0.1;
  const topThreat   = competitors.find(isThreatFn);
  const { isMobile } = useViewport();
  const cols = isMobile ? '1fr' : '1fr 1fr';

  // ── Derived insight stats (purely client-side) ──────────────────────────────
  const credibleCompetitors = competitors.filter((c) => c.review_count >= 50);
  const avgCompetitorRating =
    credibleCompetitors.length > 0
      ? credibleCompetitors.reduce((s, c) => s + c.rating, 0) / credibleCompetitors.length
      : 0;
  const ratingGap = +(myRating - avgCompetitorRating).toFixed(2);
  const ratingsAtOrAboveYou = competitors.filter((c) => c.rating >= myRating).length;
  const yourRank = ratingsAtOrAboveYou + 1; // 1-indexed
  const totalRanked = competitors.length + 1;
  const reviewVolumes = competitors.map((c) => c.review_count);
  const competitorsAboveYouOnVolume = reviewVolumes.filter((v) => v > myReviews).length;
  const volumePercentile =
    reviewVolumes.length > 0
      ? Math.round(
          (reviewVolumes.filter((v) => v <= myReviews).length / reviewVolumes.length) * 100,
        )
      : 100;
  const credibleThreats = competitors.filter(isThreatFn).length;
  const manualCount = competitors.filter((c) => c.is_manual).length;
  const autoCount = competitors.length - manualCount;

  // Top 3 by review volume — orientation around "who dominates the conversation"
  const volumeLeaders = [...competitors]
    .sort((a, b) => b.review_count - a.review_count)
    .slice(0, 3);

  // Sub-category mix (counts) — drops nulls
  const subcatCounts = competitors.reduce<Record<string, number>>((acc, c) => {
    if (!c.sub_category) return acc;
    acc[c.sub_category] = (acc[c.sub_category] ?? 0) + 1;
    return acc;
  }, {});
  const subcatEntries = Object.entries(subcatCounts).sort((a, b) => b[1] - a[1]);
  const totalSubcat = subcatEntries.reduce((s, [, n]) => s + n, 0);

  const themes = report.competitor_analysis?.themes ?? [];
  const opportunities = report.competitor_analysis?.opportunities ?? [];

  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [searching, setSearching] = useState(false);
  const [busyPid, setBusyPid] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  // Debounced autocomplete.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setSuggestions([]); return; }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const out = await searchPlaces(q);
        setSuggestions(out);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  const handleAdd = async (s: PlaceSuggestion) => {
    setBusyPid(s.place_id);
    setAddError(null);
    try {
      const c = await addCompetitor(businessId, s.place_id);
      onAdded(c);
      setQuery('');
      setSuggestions([]);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add competitor');
    } finally {
      setBusyPid(null);
    }
  };

  const handleRemove = async (placeId: string) => {
    setBusyPid(placeId);
    try {
      await removeCompetitor(businessId, placeId);
      onRemoved(placeId);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to remove competitor');
    } finally {
      setBusyPid(null);
    }
  };

  const StatTile = ({
    label, value, sub, color,
  }: { label: string; value: string; sub?: string; color: string }) => (
    <div style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ ...SEC, fontSize: 10 }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 22, color, lineHeight: 1.1 }}>{value}</span>
      {sub && <span style={{ fontSize: 11, color: 'var(--text3)' }}>{sub}</span>}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Hero strip — 4 stat tiles */}
      {competitors.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 12 }}>
          <StatTile
            label="Your Rank"
            value={`#${yourRank} of ${totalRanked}`}
            sub="by Google rating, this 800m radius"
            color={yourRank === 1 ? 'var(--emerald)' : yourRank <= Math.ceil(totalRanked / 2) ? 'var(--gold)' : 'var(--red)'}
          />
          <StatTile
            label="Rating Gap"
            value={`${ratingGap > 0 ? '+' : ''}${ratingGap.toFixed(2)}★`}
            sub={`vs avg credible competitor (${avgCompetitorRating.toFixed(1)}★)`}
            color={ratingGap >= 0 ? 'var(--emerald)' : 'var(--red)'}
          />
          <StatTile
            label="Review Volume"
            value={`${volumePercentile}th pct`}
            sub={competitorsAboveYouOnVolume > 0
              ? `${competitorsAboveYouOnVolume} have more reviews than you`
              : 'You lead on review volume'}
            color={volumePercentile >= 50 ? 'var(--emerald)' : 'var(--gold)'}
          />
          <StatTile
            label="Credible Threats"
            value={String(credibleThreats)}
            sub={credibleThreats === 0
              ? 'No competitor outranks you with ≥10% your volume'
              : 'Outrank you with credible review volume'}
            color={credibleThreats === 0 ? 'var(--emerald)' : 'var(--red)'}
          />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 16, alignItems: 'start' }}>
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
          <span style={SEC}>Nearby Competitors · 800m radius</span>
          {competitors.length > 0 && (
            <span style={{ fontSize: 10, color: 'var(--text3)' }}>
              {autoCount} auto{manualCount > 0 ? ` · ${manualCount} you added` : ''}
            </span>
          )}
        </div>

        {/* Manual-add search bar */}
        <div style={{ position: 'relative', marginBottom: 12 }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Add a competitor — search by name…"
            style={{
              width: '100%', padding: '10px 12px', fontSize: 13,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 'var(--r)', color: 'var(--text)', outline: 'none',
            }}
          />
          {query.trim().length >= 2 && (suggestions.length > 0 || searching) && (
            <div
              style={{
                position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
                background: 'var(--bg2)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 'var(--r)', zIndex: 10,
                maxHeight: 240, overflowY: 'auto',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}
            >
              {searching && suggestions.length === 0 && (
                <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text3)' }}>Searching…</div>
              )}
              {suggestions.map((s) => {
                const already = competitors.some((c) => c.place_id === s.place_id);
                return (
                  <button
                    key={s.place_id}
                    onClick={() => !already && handleAdd(s)}
                    disabled={already || busyPid === s.place_id}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: '10px 12px', fontSize: 12,
                      background: 'transparent', border: 'none',
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      color: already ? 'var(--text3)' : 'var(--text)',
                      cursor: already ? 'not-allowed' : 'pointer',
                      display: 'flex', flexDirection: 'column', gap: 2,
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>{s.name}{already ? '  · already added' : ''}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)' }}>{s.address}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {addError && (
          <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 0, marginBottom: 8 }}>{addError}</p>
        )}

        {competitors.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No nearby competitors found.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {competitors.map((c, i) => {
              const isThreat = isThreatFn(c);
              const isManual = !!c.is_manual;
              return (
                <div key={c.place_id ?? c.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px', borderRadius: 'var(--r)', background: isThreat ? 'rgba(255,95,95,0.05)' : 'transparent', border: `1px solid ${isThreat ? 'rgba(255,95,95,0.15)' : 'transparent'}` }}>
                  <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 11, color: 'var(--text3)', width: 22, flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</span>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{c.name}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 6 }}>{c.review_count.toLocaleString()} reviews</span>
                    {isManual && (
                      <span style={{ background: 'rgba(110,168,254,0.12)', border: '1px solid rgba(110,168,254,0.3)', borderRadius: 4, padding: '1px 6px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: '#6ea8fe', textTransform: 'uppercase', marginLeft: 8 }}>Added</span>
                    )}
                  </div>
                  <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13, color: isThreat ? 'var(--red)' : 'var(--text2)' }}>{c.rating}★</span>
                  {isThreat && <span style={{ background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 4, padding: '1px 6px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--red)', textTransform: 'uppercase' }}>THREAT</span>}
                  {isManual && c.place_id && (
                    <button
                      onClick={() => handleRemove(c.place_id!)}
                      disabled={busyPid === c.place_id}
                      title="Remove"
                      style={{
                        background: 'transparent', border: 'none',
                        color: 'var(--text3)', cursor: 'pointer',
                        fontSize: 16, lineHeight: 1, padding: '0 4px',
                      }}
                    >×</button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={CARD}>
        <span style={SEC}>Rating Comparison</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 12 }}>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{report.business_name} <span style={{ fontSize: 10, color: 'var(--text3)', fontWeight: 400 }}>(you)</span></span>
              <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, color: 'var(--gold)' }}>{myRating}★</span>
            </div>
            <div style={{ height: 7, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ width: `${(myRating / 5) * 100}%`, height: '100%', background: 'var(--gold)', borderRadius: 999 }} />
            </div>
          </div>
          {competitors.map((c) => {
            const barColor = c.rating > myRating ? 'var(--red)' : 'var(--violet)';
            return (
              <div key={c.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 12 }}>
                  <span style={{ color: 'var(--text2)' }}>{c.name}</span>
                  <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, color: barColor }}>{c.rating}★</span>
                </div>
                <div style={{ height: 7, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: `${(c.rating / 5) * 100}%`, height: '100%', background: barColor, borderRadius: 999 }} />
                </div>
              </div>
            );
          })}
        </div>
        {topThreat && (
          <div style={{ marginTop: 20, background: 'var(--red-dim)', border: '1px solid rgba(255,95,95,0.25)', borderRadius: 'var(--r)', padding: '12px 14px', fontSize: 12, color: 'var(--text2)', lineHeight: 1.6 }}>
            <span style={{ color: 'var(--red)', fontWeight: 600 }}>{topThreat.name}</span> at {topThreat.rating}★ is your highest-rated nearby competitor. A {(topThreat.rating - myRating).toFixed(1)}★ gap to close
            {topThreat.review_count > myReviews && (
              <> · they also have {(topThreat.review_count / Math.max(myReviews, 1)).toFixed(1)}× your review volume.</>
            )}
          </div>
        )}
      </div>
      </div>

      {/* Themes + Opportunities */}
      {(themes.length > 0 || opportunities.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 16, alignItems: 'start' }}>
          <div style={CARD}>
            <span style={SEC}>What competitors are praised for</span>
            {themes.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No themes available.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {themes.map((t, i) => (
                  <li key={i} style={{ display: 'flex', gap: 10, fontSize: 12, lineHeight: 1.55, color: 'var(--text2)' }}>
                    <span style={{ fontFamily: 'var(--font-space-mono), monospace', color: 'var(--gold)', fontSize: 11, flexShrink: 0, marginTop: 1 }}>{String(i + 1).padStart(2, '0')}</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div style={CARD}>
            <span style={SEC}>Gaps you can exploit</span>
            {opportunities.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No gap signals from current competitor reviews.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {opportunities.map((o, i) => (
                  <li key={i} style={{ display: 'flex', gap: 10, fontSize: 12, lineHeight: 1.55, color: 'var(--text2)' }}>
                    <span style={{ fontFamily: 'var(--font-space-mono), monospace', color: 'var(--emerald)', fontSize: 11, flexShrink: 0, marginTop: 1 }}>{String(i + 1).padStart(2, '0')}</span>
                    <span>{o}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Volume leaders + Sub-category mix */}
      {competitors.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 16, alignItems: 'start' }}>
          <div style={CARD}>
            <span style={SEC}>Volume leaders · who dominates the conversation</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {volumeLeaders.map((c, i) => {
                const ratio = myReviews > 0 ? c.review_count / myReviews : null;
                const ratioText = ratio == null
                  ? `${c.review_count.toLocaleString()} reviews`
                  : ratio >= 1
                    ? `${ratio.toFixed(1)}× your reviews`
                    : `${(ratio * 100).toFixed(0)}% of your reviews`;
                return (
                  <div key={c.place_id ?? c.name} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 11, color: 'var(--text3)', width: 22, flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
                        <span style={{ color: 'var(--text)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                        <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, color: 'var(--violet)' }}>{c.review_count.toLocaleString()}</span>
                      </div>
                      <div style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{
                          width: `${Math.min(100, (c.review_count / Math.max(volumeLeaders[0].review_count, 1)) * 100)}%`,
                          height: '100%', background: 'var(--violet)', borderRadius: 999,
                        }} />
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text3)' }}>{ratioText}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div style={CARD}>
            <span style={SEC}>Competitor mix by sub-category</span>
            {subcatEntries.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>Sub-category data not available for this category.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {subcatEntries.map(([cat, n], i) => {
                  const pct = (n / totalSubcat) * 100;
                  const color = CAT_COLORS[i % CAT_COLORS.length];
                  return (
                    <div key={cat}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
                        <span style={{ color: 'var(--text2)', textTransform: 'capitalize' }}>{cat.replace(/_/g, ' ')}</span>
                        <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, color }}>{n}</span>
                      </div>
                      <div style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 999 }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── POS DASHBOARD HELPERS ─────────────────────────────────────────────────────

const fmtINR = (n: number): string => {
  const sign = n < 0 ? '-' : '';
  const x = Math.abs(n);
  if (x >= 10000000) return `${sign}₹${(x / 10000000).toFixed(2)}Cr`;
  if (x >= 100000)   return `${sign}₹${(x / 100000).toFixed(2)}L`;
  if (x >= 1000)     return `${sign}₹${(x / 1000).toFixed(1)}k`;
  return `${sign}₹${Math.round(x)}`;
};

const fmtINRShort = (n: number): string => {
  const x = Math.abs(n);
  if (x >= 100000) return `${n < 0 ? '-' : ''}${(x / 100000).toFixed(1)}L`;
  if (x >= 1000)   return `${n < 0 ? '-' : ''}${Math.round(x / 1000)}k`;
  return Math.round(n).toString();
};

const fmtINRFull = (n: number): string =>
  `₹${Math.round(n).toLocaleString('en-IN')}`;

// Tiny KPI tile used at the top of the dashboard.
function KpiCard({
  label, value, sub, color = 'var(--text)', subColor,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  subColor?: string;
}) {
  return (
    <div style={{ ...CARD, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text3)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 22, color, lineHeight: 1.15, wordBreak: 'break-word' }}>{value}</span>
      {sub && <span style={{ fontSize: 11, color: subColor ?? 'var(--text3)', lineHeight: 1.3 }}>{sub}</span>}
    </div>
  );
}

// Simple growth-percentage badge (+5.2%, -3.4%, neutral).
function GrowthBadge({ pct }: { pct: number | null }) {
  if (pct == null) {
    return <span style={{ fontSize: 10, color: 'var(--text3)' }}>—</span>;
  }
  const positive = pct > 0;
  const neutral  = pct === 0;
  const color = neutral ? 'var(--text3)' : positive ? 'var(--emerald)' : 'var(--red)';
  const dim   = neutral ? 'rgba(255,255,255,0.06)' : positive ? 'rgba(16,217,160,0.12)' : 'rgba(255,95,95,0.12)';
  const arrow = neutral ? '→' : positive ? '↑' : '↓';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 700, color, background: dim, border: `1px solid ${color}`, borderRadius: 999, padding: '1px 7px', fontFamily: 'var(--font-space-mono), monospace' }}>
      {arrow} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

// Daily revenue area chart — SVG, smooth-ish line through the points + filled area.
function DailyRevenueChart({ data, height = 160 }: { data: { date: string; revenue: number; orders: number }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length === 0) return null;
  const W = 800;
  const H = height;
  const pad = { top: 12, right: 12, bottom: 22, left: 8 };
  const xs = data.map((_, i) => pad.left + (i * (W - pad.left - pad.right)) / Math.max(1, data.length - 1));
  const max = Math.max(1, ...data.map(d => d.revenue));
  const ys = data.map(d => pad.top + (1 - d.revenue / max) * (H - pad.top - pad.bottom));
  const lineD = data.map((_, i) => `${i === 0 ? 'M' : 'L'} ${xs[i].toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');
  const areaD = `${lineD} L ${xs[xs.length - 1].toFixed(1)} ${(H - pad.bottom).toFixed(1)} L ${xs[0].toFixed(1)} ${(H - pad.bottom).toFixed(1)} Z`;

  // Show ~6 x-axis ticks evenly spaced.
  const tickCount = Math.min(6, data.length);
  const tickIdx = Array.from({ length: tickCount }, (_, i) =>
    Math.round((i * (data.length - 1)) / Math.max(1, tickCount - 1))
  );

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height, display: 'block' }}>
        <defs>
          <linearGradient id="dailyArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="var(--violet)" stopOpacity={0.45} />
            <stop offset="100%" stopColor="var(--violet)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={areaD} fill="url(#dailyArea)" />
        <path d={lineD} stroke="var(--violet)" strokeWidth={1.5} fill="none" />
        {data.map((_, i) => (
          <circle
            key={i}
            cx={xs[i]} cy={ys[i]} r={hover === i ? 3.5 : 2}
            fill={hover === i ? 'var(--violet)' : 'transparent'}
            stroke={hover === i ? 'var(--violet)' : 'transparent'}
            strokeWidth={1.5}
          />
        ))}
        {/* Wide invisible hover columns */}
        {data.map((_, i) => (
          <rect
            key={`h${i}`}
            x={xs[i] - (W / data.length) / 2}
            y={0}
            width={W / data.length}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        {tickIdx.map(i => (
          <text key={`t${i}`} x={xs[i]} y={H - 4} fontSize={9} fill="var(--text3)" textAnchor="middle" fontFamily="var(--font-space-mono), monospace">
            {data[i].date.slice(5)}
          </text>
        ))}
      </svg>
      {hover !== null && (
        <div style={{ position: 'absolute', top: 4, left: `${(xs[hover] / W) * 100}%`, transform: 'translateX(-50%)', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: 'var(--text)', whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 10 }}>
          <div style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 10, color: 'var(--text3)' }}>{data[hover].date}</div>
          <div style={{ fontFamily: 'var(--font-space-mono), monospace', fontWeight: 700 }}>{fmtINRFull(data[hover].revenue)}</div>
          <div style={{ fontSize: 10, color: 'var(--text3)' }}>{data[hover].orders} orders</div>
        </div>
      )}
    </div>
  );
}

// Weekly revenue bar chart with growth badges below each bar.
function WeeklyRevenueChart({ data, height = 140 }: { data: import('@/lib/api').WeeklyRevenuePoint[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length === 0) return null;
  const max = Math.max(1, ...data.map(d => d.revenue));
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height }}>
        {data.map((d, i) => {
          const h = Math.max(2, (d.revenue / max) * (height - 4));
          const isHover = hover === i;
          return (
            <div
              key={d.week_start}
              style={{ flex: 1, height, position: 'relative', cursor: 'default' }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {isHover && (
                <div style={{ position: 'absolute', bottom: h + 6, left: '50%', transform: 'translateX(-50%)', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 5, padding: '3px 9px', fontSize: 10, fontFamily: 'var(--font-space-mono), monospace', color: 'var(--text)', whiteSpace: 'nowrap', zIndex: 10 }}>
                  {fmtINRFull(d.revenue)} · {d.orders} orders
                </div>
              )}
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: h, background: d.growth_pct != null && d.growth_pct < 0 ? 'var(--red)' : 'var(--violet)', opacity: isHover ? 1 : 0.7, borderRadius: '4px 4px 0 0', transition: 'height 500ms cubic-bezier(0.4,0,0.2,1), opacity 150ms' }} />
            </div>
          );
        })}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
        {data.map(d => (
          <span key={`l${d.week_start}`} style={{ flex: 1, textAlign: 'center', fontSize: 9, fontFamily: 'var(--font-space-mono), monospace', color: 'var(--text3)' }}>
            {d.label}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
        {data.map((d, i) => (
          <div key={`g${d.week_start}`} style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
            {i > 0 && <GrowthBadge pct={d.growth_pct} />}
          </div>
        ))}
      </div>
    </div>
  );
}

// Day-of-week revenue (Mon–Sun avg).
function DowChart({ data, height = 130 }: { data: import('@/lib/api').PeakDayEntry[]; height?: number }) {
  if (data.length === 0) return null;
  const max = Math.max(1, ...data.map(d => d.avg_revenue));
  const peakDay = data.reduce((a, b) => (a.avg_revenue >= b.avg_revenue ? a : b));
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height }}>
        {data.map(d => {
          const h = Math.max(2, (d.avg_revenue / max) * (height - 4));
          const isPeak = d.day === peakDay.day;
          return (
            <div key={d.day} style={{ flex: 1, height, position: 'relative' }}>
              <div style={{ position: 'absolute', top: -16, left: 0, right: 0, textAlign: 'center', fontSize: 9, fontFamily: 'var(--font-space-mono), monospace', color: isPeak ? 'var(--gold)' : 'var(--text3)', fontWeight: isPeak ? 700 : 400 }}>
                {fmtINRShort(d.avg_revenue)}
              </div>
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: h, background: isPeak ? 'var(--gold)' : 'var(--emerald)', opacity: isPeak ? 1 : 0.55, borderRadius: '4px 4px 0 0' }} />
            </div>
          );
        })}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
        {data.map(d => (
          <span key={`d${d.day}`} style={{ flex: 1, textAlign: 'center', fontSize: 10, fontWeight: 600, color: d.day === peakDay.day ? 'var(--gold)' : 'var(--text2)' }}>
            {d.day}
          </span>
        ))}
      </div>
    </div>
  );
}

// SVG donut for revenue by category.
function CategoryDonut({ data, size = 160 }: { data: { name: string; revenue: number; pct: number }[]; size?: number }) {
  if (data.length === 0) return null;
  const total = data.reduce((s, d) => s + d.revenue, 0) || 1;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 6;
  const inner = r * 0.62;
  const arcs: { d: string; color: string; name: string; pct: number }[] = [];
  let a = -Math.PI / 2;
  data.forEach((d, i) => {
    const slice = (d.revenue / total) * 2 * Math.PI;
    const aEnd = a + slice;
    const large = slice > Math.PI ? 1 : 0;
    const x1 = cx + r * Math.cos(a);
    const y1 = cy + r * Math.sin(a);
    const x2 = cx + r * Math.cos(aEnd);
    const y2 = cy + r * Math.sin(aEnd);
    const x3 = cx + inner * Math.cos(aEnd);
    const y3 = cy + inner * Math.sin(aEnd);
    const x4 = cx + inner * Math.cos(a);
    const y4 = cy + inner * Math.sin(a);
    arcs.push({
      d: `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${inner} ${inner} 0 ${large} 0 ${x4} ${y4} Z`,
      color: CAT_COLORS[i % CAT_COLORS.length],
      name: d.name,
      pct: d.pct,
    });
    a = aEnd;
  });
  const totalRev = data.reduce((s, d) => s + d.revenue, 0);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
        {arcs.map((arc, i) => (
          <path key={i} d={arc.d} fill={arc.color} opacity={0.9} />
        ))}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize={10} fill="var(--text3)" letterSpacing="0.1em">TOTAL</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize={14} fontWeight={700} fill="var(--text)" fontFamily="var(--font-space-grotesk), sans-serif">
          {fmtINR(totalRev)}
        </text>
      </svg>
      <div style={{ flex: 1, minWidth: 140, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {arcs.map((arc, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: arc.color, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: 'var(--text2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{arc.name}</span>
            <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-space-mono), monospace' }}>{arc.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── TAB: POS ──────────────────────────────────────────────────────────────────
function PosTab({ businessId }: { businessId: string }) {
  const { isMobile } = useViewport();
  const [data, setData]       = useState<PosDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  // User-controlled filters (empty = unfiltered).
  const [from, setFrom]         = useState<string>('');
  const [to, setTo]             = useState<string>('');
  const [category, setCategory] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPosDashboard(businessId, from || undefined, to || undefined, category || undefined)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [businessId, from, to, category]);

  const empty =
    !loading &&
    data != null &&
    data.metrics.total_orders === 0 &&
    data.daily_revenue.length === 0;

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Skeleton height={48} />
        <Skeleton height={120} />
        <Skeleton height={220} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ ...CARD, borderColor: 'var(--red)', background: 'var(--red-dim)' }}>
        <p style={{ fontSize: 13, color: 'var(--red)', margin: 0 }}>Dashboard unavailable: {error}</p>
      </div>
    );
  }

  if (!data || empty) {
    return (
      <div style={{ ...CARD, textAlign: 'center', padding: '40px 24px' }}>
        <p style={{ fontSize: 14, color: 'var(--text2)', margin: '0 0 6px' }}>
          {category || from || to ? 'No POS data matches these filters.' : 'No POS data yet.'}
        </p>
        <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>
          {category || from || to
            ? 'Try removing a filter or widening the date range.'
            : `Upload a CSV via the onboarding flow to populate this tab.`}
        </p>
        {(category || from || to) && (
          <button
            onClick={() => { setFrom(''); setTo(''); setCategory(''); }}
            style={{ ...GHOST_BTN, marginTop: 16 }}
          >
            Reset filters
          </button>
        )}
      </div>
    );
  }

  const m = data.metrics;
  const filterRowCols = isMobile ? '1fr' : '1fr 1fr 1fr auto';
  const cardGridCols  = isMobile ? '1fr 1fr' : 'repeat(6, 1fr)';
  const splitCols     = isMobile ? '1fr' : '1fr 1fr';

  // Day name from ISO week_start (week starting Sunday in our backend grouping).
  const formatWeekRange = (w: import('@/lib/api').WeeklyRevenuePoint | null): string => {
    if (!w) return '—';
    return `${w.label} · ${w.week_start}`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* ── Filter bar ────────────────────────────────────────────────────── */}
      <div style={{ ...CARD, padding: '12px 16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: filterRowCols, gap: 10, alignItems: 'end' }}>
          <div>
            <span style={{ ...SEC, margin: '0 0 4px' }}>From</span>
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => setFrom(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontSize: 12, fontFamily: 'inherit' }}
            />
          </div>
          <div>
            <span style={{ ...SEC, margin: '0 0 4px' }}>To</span>
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => setTo(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontSize: 12, fontFamily: 'inherit' }}
            />
          </div>
          <div>
            <span style={{ ...SEC, margin: '0 0 4px' }}>Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontSize: 12, fontFamily: 'inherit' }}
            >
              <option value="">All categories</option>
              {data.categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          {(from || to || category) && (
            <button onClick={() => { setFrom(''); setTo(''); setCategory(''); }} style={GHOST_BTN}>
              Reset
            </button>
          )}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text3)' }}>
          Showing <strong style={{ color: 'var(--text2)' }}>{m.date_range.from}</strong> → <strong style={{ color: 'var(--text2)' }}>{m.date_range.to}</strong> ({m.date_range.days} days){category ? ` · ${category}` : ''}
        </div>
      </div>

      {/* ── KPI cards ─────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: cardGridCols, gap: 12 }}>
        <KpiCard label="Total Revenue" value={fmtINR(m.total_revenue)} sub={fmtINRFull(m.total_revenue)} color="var(--emerald)" />
        <KpiCard label="Total Orders"  value={m.total_orders.toLocaleString('en-IN')} sub={`${m.total_units.toLocaleString('en-IN')} items sold`} color="var(--violet)" />
        <KpiCard label="Avg Order Value" value={fmtINR(m.avg_order_value)} sub="per order" color="var(--gold)" />
        <KpiCard label="Avg Daily Revenue" value={fmtINR(m.avg_daily_revenue)} sub={`across ${m.date_range.days} days`} color="var(--text)" />
        <KpiCard label="Best-Selling Item" value={m.best_selling_item ?? '—'} sub={m.best_selling_revenue > 0 ? fmtINR(m.best_selling_revenue) : undefined} color="var(--text)" />
        <KpiCard label="Total Expenses" value="—" sub="not tracked" color="var(--text3)" />
      </div>

      {/* ── Daily revenue trend (full width) ──────────────────────────────── */}
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10, gap: 12, flexWrap: 'wrap' }}>
          <span style={SEC}>Daily Revenue Trend</span>
          <span style={{ fontSize: 11, color: 'var(--text3)' }}>
            {data.daily_revenue.length} days · hover to inspect
          </span>
        </div>
        <DailyRevenueChart data={data.daily_revenue} height={isMobile ? 140 : 180} />
      </div>

      {/* ── Weekly revenue + Peak day side by side ───────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: splitCols, gap: 16, alignItems: 'start' }}>
        <div style={CARD}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10, gap: 12 }}>
            <span style={SEC}>Weekly Revenue & Growth</span>
            <span style={{ fontSize: 11, color: 'var(--text3)' }}>
              week-over-week
            </span>
          </div>
          <WeeklyRevenueChart data={data.weekly_revenue} height={130} />
        </div>
        <div style={CARD}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 18, gap: 12 }}>
            <span style={SEC}>Peak Sales Day</span>
            <span style={{ fontSize: 11, color: 'var(--text3)' }}>
              avg per weekday
            </span>
          </div>
          <DowChart data={data.peak_day_of_week} height={130} />
        </div>
      </div>

      {/* ── Best/Worst week + Most popular category ──────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: splitCols, gap: 16, alignItems: 'start' }}>
        <div style={CARD}>
          <span style={SEC}>Best & Worst Performing Week</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', background: 'rgba(16,217,160,0.08)', border: '1px solid rgba(16,217,160,0.25)', borderRadius: 'var(--r)' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--emerald)', color: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13 }}>↑</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--emerald)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Best Week</span>
                <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700 }}>
                  {data.weekly_growth.best_week ? fmtINRFull(data.weekly_growth.best_week.revenue) : '—'}
                </p>
                <span style={{ fontSize: 11, color: 'var(--text3)' }}>{formatWeekRange(data.weekly_growth.best_week)}</span>
              </div>
              {data.weekly_growth.best_week && <GrowthBadge pct={data.weekly_growth.best_week.growth_pct} />}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', background: 'rgba(255,95,95,0.06)', border: '1px solid rgba(255,95,95,0.22)', borderRadius: 'var(--r)' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--red)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13 }}>↓</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--red)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Worst Week</span>
                <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700 }}>
                  {data.weekly_growth.worst_week ? fmtINRFull(data.weekly_growth.worst_week.revenue) : '—'}
                </p>
                <span style={{ fontSize: 11, color: 'var(--text3)' }}>{formatWeekRange(data.weekly_growth.worst_week)}</span>
              </div>
              {data.weekly_growth.worst_week && <GrowthBadge pct={data.weekly_growth.worst_week.growth_pct} />}
            </div>
          </div>
        </div>

        <div style={CARD}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14, gap: 12 }}>
            <span style={SEC}>Revenue by Category</span>
            <span style={{ fontSize: 11, color: 'var(--text3)' }}>
              {data.revenue_by_category[0] ? `Top: ${data.revenue_by_category[0].name}` : ''}
            </span>
          </div>
          <CategoryDonut data={data.revenue_by_category} size={isMobile ? 130 : 160} />
        </div>
      </div>
    </div>
  );
}

// ─── TAB: History ──────────────────────────────────────────────────────────────
function HistoryTab({ scores, error }: { scores: HistoryEntry[]; error: string | null }) {
  if (error) {
    return (
      <div style={{ maxWidth: 560 }}>
        <div style={{ ...CARD, borderColor: 'var(--red)', background: 'var(--red-dim)' }}>
          <p style={{ fontSize: 13, color: 'var(--red)', margin: 0 }}>History unavailable: {error}</p>
        </div>
      </div>
    );
  }

  if (scores.length === 0) {
    return (
      <div style={{ maxWidth: 560 }}>
        <div style={CARD}>
          <p style={{ fontSize: 13, color: 'var(--text3)', margin: 0, textAlign: 'center', padding: '20px 0' }}>No history yet — generate your first report to start tracking.</p>
        </div>
      </div>
    );
  }

  const latest = scores[0];
  const oldest = scores[scores.length - 1];
  const delta  = latest.final_score - oldest.final_score;

  return (
    <div style={{ maxWidth: 560 }}>
      <div style={CARD}>
        <span style={SEC}>Health Score History</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {scores.map((h, i) => {
            const band = scoreToBand(h.final_score);
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 11, color: 'var(--text3)', width: 52, flexShrink: 0 }}>{toWeekLabel(h.created_at)}</span>
                <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: `${h.final_score}%`, height: '100%', background: BAND_COLOR[band], borderRadius: 999 }} />
                </div>
                <div style={{ width: 38, height: 26, background: BAND_DIM[band], border: `1px solid ${BAND_COLOR[band]}`, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 12, color: BAND_COLOR[band], flexShrink: 0 }}>
                  {h.final_score}
                </div>
                {i === 0 ? (
                  <span style={{ background: 'var(--emerald-dim)', border: '1px solid var(--emerald)', borderRadius: 4, padding: '1px 6px', fontSize: 9, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--emerald)', flexShrink: 0 }}>LATEST</span>
                ) : (
                  <span style={{ width: 47, flexShrink: 0 }} />
                )}
              </div>
            );
          })}
        </div>
        {scores.length > 1 && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 8, background: delta >= 0 ? 'var(--emerald-dim)' : 'var(--red-dim)', border: `1px solid ${delta >= 0 ? 'var(--emerald)' : 'var(--red)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width={12} height={12} viewBox="0 0 12 12" fill="none" stroke={delta >= 0 ? 'var(--emerald)' : 'var(--red)'} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                {delta >= 0
                  ? <polyline points="1,9 5,4 8,6 11,2" />
                  : <polyline points="1,3 5,8 8,6 11,10" />}
              </svg>
            </div>
            <span style={{ fontSize: 13, color: 'var(--text2)' }}>
              <span style={{ color: delta >= 0 ? 'var(--emerald)' : 'var(--red)', fontWeight: 600 }}>
                {delta >= 0 ? '+' : ''}{delta} points
              </span>{' '}
              over {scores.length} weeks
            </span>
            <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 2 }}>— {BAND_LABEL[scoreToBand(latest.final_score)]}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── TAB: Notes ────────────────────────────────────────────────────────────────
function NotesTab({ ctx }: { ctx: ActionsCtx }) {
  const saved     = ctx.actions.filter((a) => a.kind === 'insight_saved');
  const actioned  = ctx.actions.filter((a) => a.kind === 'insight_actioned');
  const completed = ctx.actions.filter((a) => a.kind === 'weekly_action_done');

  const total = saved.length + actioned.length + completed.length;

  const [busyId, setBusyId] = useState<string | null>(null);
  const remove = async (id: string) => {
    if (busyId) return;
    setBusyId(id);
    try { await ctx.onDelete(id); }
    finally { setBusyId(null); }
  };

  if (total === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 720 }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 3px' }}>
            Notes
          </h2>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>Saved insights, actioned items, and completed weekly actions</span>
        </div>
        <div style={{ ...CARD, textAlign: 'center', padding: '40px 20px' }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--surface2)', border: '1px solid var(--border)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14 }}>
            <svg width={20} height={20} viewBox="0 0 20 20" fill="none" stroke="var(--text3)" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z" /><line x1={7} y1={6} x2={13} y2={6} /><line x1={7} y1={9} x2={13} y2={9} /><line x1={7} y1={12} x2={11} y2={12} />
            </svg>
          </div>
          <h3 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 15, color: 'var(--text)', margin: '0 0 6px' }}>No notes yet</h3>
          <p style={{ fontSize: 13, color: 'var(--text3)', margin: 0, lineHeight: 1.6, maxWidth: 360, marginInline: 'auto' }}>
            Click <strong style={{ color: 'var(--text2)' }}>Save to Notes</strong> on any insight, <strong style={{ color: 'var(--text2)' }}>Mark Actioned</strong> to track progress, or <strong style={{ color: 'var(--text2)' }}>Mark Done</strong> on weekly actions. They&apos;ll all show up here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 720 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 3px' }}>
            Notes
          </h2>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            {saved.length} saved · {actioned.length} actioned · {completed.length} completed
          </span>
        </div>
      </div>

      {/* Saved insights with notes */}
      {saved.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ ...SEC, color: 'var(--violet)' }}>📝 Saved Insights · {saved.length}</span>
          {saved.map((a) => (
            <div key={a.id} style={{ ...CARD, borderColor: 'rgba(139,111,255,0.22)', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, lineHeight: 1.65 }}>{a.target_text}</p>
              {a.note && (
                <div style={{ padding: '8px 12px', background: 'var(--violet-dim)', border: '1px solid rgba(139,111,255,0.25)', borderRadius: 'var(--r)' }}>
                  <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--violet)', display: 'block', marginBottom: 3 }}>Your note</span>
                  <p style={{ fontSize: 12, color: 'var(--text2)', margin: 0, lineHeight: 1.55 }}>{a.note}</p>
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--text3)' }}>
                <span>Saved {formatRelativeTime(a.created_at)}</span>
                <button onClick={() => remove(a.id)} disabled={busyId === a.id} style={{ ...GHOST_BTN, padding: '3px 10px', fontSize: 10 }}>
                  {busyId === a.id ? '…' : 'Remove'}
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Actioned insights — track record */}
      {actioned.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ ...SEC, color: 'var(--emerald)' }}>✓ Actioned Insights · {actioned.length}</span>
          {actioned.map((a) => (
            <div key={a.id} style={{ ...CARD, padding: '14px 18px', borderColor: 'rgba(16,217,160,0.22)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flexShrink: 0, marginTop: 2, width: 18, height: 18, borderRadius: '50%', background: 'var(--emerald-dim)', border: '1.5px solid var(--emerald)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width={10} height={10} viewBox="0 0 12 12" fill="none" stroke="var(--emerald)" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="2,6 5,9 10,3" />
                </svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 13, color: 'var(--text2)', margin: 0, lineHeight: 1.6, textDecoration: 'line-through', opacity: 0.85 }}>{a.target_text}</p>
                <span style={{ fontSize: 11, color: 'var(--text3)', display: 'block', marginTop: 5 }}>Actioned {formatRelativeTime(a.created_at)}</span>
              </div>
              <button onClick={() => remove(a.id)} disabled={busyId === a.id} style={{ ...GHOST_BTN, padding: '3px 10px', fontSize: 10, flexShrink: 0 }}>
                {busyId === a.id ? '…' : 'Undo'}
              </button>
            </div>
          ))}
        </section>
      )}

      {/* Completed weekly actions */}
      {completed.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ ...SEC, color: 'var(--gold)' }}>⚡ Completed Weekly Actions · {completed.length}</span>
          {completed.map((a) => (
            <div key={a.id} style={{ ...CARD, padding: '14px 18px', borderColor: 'rgba(245,166,35,0.22)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flexShrink: 0, width: 28, height: 28, borderRadius: 8, background: 'var(--emerald)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="black" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="2.5,7 5.5,10 11.5,3.5" />
                </svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, lineHeight: 1.6 }}>{a.target_text}</p>
                <span style={{ fontSize: 11, color: 'var(--text3)', display: 'block', marginTop: 5 }}>Completed {formatRelativeTime(a.created_at)}</span>
              </div>
              <button onClick={() => remove(a.id)} disabled={busyId === a.id} style={{ ...GHOST_BTN, padding: '3px 10px', fontSize: 10, flexShrink: 0 }}>
                {busyId === a.id ? '…' : 'Undo'}
              </button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

// ─── Dashboard Page ─────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router           = useRouter();
  const { businessId, bizLoading, clearBusinessId } = useBusinessId();
  const { user, loading: authLoading, signOut } = useAuth();

  const [report,       setReport]       = useState<HealthReport | null>(null);
  const [histScores,   setHistScores]   = useState<HistoryEntry[]>([]);
  const [actions,      setActions]      = useState<ActionEntry[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [histError,    setHistError]    = useState<string | null>(null);
  const [refreshing,   setRefreshing]   = useState(false);
  const [toast,        setToast]        = useState(false);
  const [tab,          setTab]          = useState<Tab>('overview');
  const [hoveredTab,   setHoveredTab]   = useState<Tab | null>(null);
  const [menuOpen,     setMenuOpen]     = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const { isMobile } = useViewport();

  const handleLogAction = useCallback(async (kind: ActionEntry['kind'], targetText: string, note?: string) => {
    if (!businessId) return;
    const entry = await logAction(businessId, kind, targetText, note);
    setActions((prev) => [entry, ...prev]);
  }, [businessId]);

  const handleDeleteAction = useCallback(async (id: string) => {
    await deleteAction(id);
    setActions((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const actionsCtx: ActionsCtx = {
    actions,
    onLog: handleLogAction,
    onDelete: handleDeleteAction,
  };

  const fetchAll = useCallback(async (id: string, force = false) => {
    const MAX_ATTEMPTS = 2;
    const fetchReport = async () => {
      let lastErr: unknown = null;
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        try { return await generateReport(id, force); }
        catch (e) {
          lastErr = e;
          if (attempt < MAX_ATTEMPTS - 1) await new Promise((r) => setTimeout(r, 1500));
        }
      }
      throw lastErr;
    };

    try {
      const [rep, hist, acts] = await Promise.allSettled([
        fetchReport(),
        getHistory(id, 12),
        getActions(id),
      ]);

      if (rep.status === 'fulfilled') {
        setReport(rep.value);
        setError(null);
      } else {
        setError(rep.reason instanceof Error ? rep.reason.message : String(rep.reason));
      }

      if (hist.status === 'fulfilled') {
        setHistScores(hist.value.scores);
        setHistError(null);
      } else {
        setHistError(hist.reason instanceof Error ? hist.reason.message : String(hist.reason));
      }

      if (acts.status === 'fulfilled') {
        setActions(acts.value.actions);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || bizLoading) return;
    if (!user) { router.push('/login'); return; }
    if (!businessId) { router.push('/onboard/pos'); return; }
    fetchAll(businessId);
  }, [authLoading, bizLoading, user, businessId, fetchAll, router]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleRefresh = async () => {
    if (!businessId || refreshing) return;
    setRefreshing(true);
    try {
      const rep = await generateReport(businessId, true);
      setReport(rep);
      setError(null);
      setToast(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>

      {/* ── Nav ────────────────────────────────────────── */}
      <nav style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--nav-bg)', backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)', borderBottom: '1px solid var(--border)', height: 60, display: 'flex', alignItems: 'center', padding: isMobile ? '0 12px' : '0 20px', gap: isMobile ? 8 : 12 }}>
        <Logo size={isMobile ? 22 : 26} />

        <div style={{
          display: 'flex', gap: 2, flex: 1,
          justifyContent: isMobile ? 'flex-start' : 'center',
          overflowX: 'auto', overflowY: 'hidden',
          scrollbarWidth: 'none', msOverflowStyle: 'none',
        }} className="hide-scrollbar">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              onMouseEnter={() => setHoveredTab(t.id)} onMouseLeave={() => setHoveredTab(null)}
              style={{ padding: isMobile ? '6px 10px' : '6px 14px', borderRadius: 8, border: 'none', background: tab === t.id ? 'rgba(255,255,255,0.08)' : 'transparent', color: tab === t.id ? 'var(--text)' : hoveredTab === t.id ? 'var(--text2)' : 'var(--text3)', fontWeight: tab === t.id ? 600 : 400, fontSize: isMobile ? 12 : 13, cursor: 'pointer', transition: 'background 150ms, color 150ms', fontFamily: 'inherit', whiteSpace: 'nowrap', flexShrink: 0 }}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 6 : 8, flexShrink: 0 }}>
          <ThemeToggle />
          <button onClick={handleRefresh} disabled={refreshing} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: isMobile ? '6px 8px' : '5px 11px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text2)', fontSize: 12, cursor: refreshing ? 'not-allowed' : 'pointer', fontFamily: 'inherit', opacity: refreshing ? 0.6 : 1, transition: 'opacity 150ms' }}>
            {refreshing ? <Spin size={12} /> : (
              <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
                <path d="M1 4v6h6" /><path d="M23 20v-6h-6" />
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15" />
              </svg>
            )}
            {!isMobile && 'Refresh'}
          </button>
          {!isMobile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'var(--emerald-dim)', border: '1px solid rgba(16,217,160,0.25)', borderRadius: 999, padding: '4px 10px', fontSize: 11, fontWeight: 500, color: 'var(--emerald)' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--emerald)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block', flexShrink: 0 }} />
              Mon 8AM
            </div>
          )}
          {/* Avatar + dropdown */}
          <div ref={menuRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              style={{ width: 32, height: 32, borderRadius: '50%', background: 'linear-gradient(135deg, var(--violet), var(--gold))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 14, color: '#fff', flexShrink: 0, cursor: 'pointer', border: 'none' }}
            >
              {userDisplayName(user)[0]?.toUpperCase() ?? 'U'}
            </button>

            {menuOpen && (
              <div style={{
                position: 'absolute', top: 40, right: 0, width: 220,
                background: 'var(--bg2)', border: '1px solid var(--border2)',
                borderRadius: 'var(--r)', boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                overflow: 'hidden', zIndex: 300,
                animation: 'fadeUp 0.15s ease both',
              }}>
                {/* User info */}
                <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
                  {userDisplayName(user) && (
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-space-grotesk), sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: 2 }}>
                      {userDisplayName(user)}
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'inherit', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {user?.email}
                  </div>
                </div>

                {/* Connections */}
                <button
                  onClick={() => { setMenuOpen(false); router.push('/profile/connections'); }}
                  style={{ width: '100%', padding: '10px 14px', background: 'transparent', border: 'none', borderBottom: '1px solid var(--border)', cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--text2)', fontFamily: 'inherit' }}
                >
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                  </svg>
                  Connections
                </button>

                {/* Re-do onboarding */}
                <button
                  onClick={() => { clearBusinessId(); setMenuOpen(false); router.push('/onboard/pos'); }}
                  style={{ width: '100%', padding: '10px 14px', background: 'transparent', border: 'none', borderBottom: '1px solid var(--border)', cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--text2)', fontFamily: 'inherit' }}
                >
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                    <path d="M3 3v5h5" />
                  </svg>
                  Re-do Setup
                </button>

                {/* Sign out */}
                <button
                  onClick={async () => { setMenuOpen(false); await signOut(); router.push('/login'); }}
                  style={{ width: '100%', padding: '10px 14px', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--red)', fontFamily: 'inherit' }}
                >
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* ── Page header ────────────────────────────────── */}
      <div style={{ padding: isMobile ? '16px 12px 0' : '20px 24px 0', display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'flex-start', justifyContent: 'space-between', gap: isMobile ? 8 : 12 }}>
        <div>
          {loading ? (
            <>
              <Skeleton height={22} width={200} style={{ marginBottom: 6, borderRadius: 6 }} />
              <Skeleton height={12} width={280} style={{ borderRadius: 4 }} />
            </>
          ) : (
            <>
              <h1 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 26, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 4px' }}>
                {report?.business_name ?? '—'}
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13, color: 'var(--text3)' }}>
                  {[report?.address, report?.category, report?.owner_name].filter(Boolean).join(' · ') || 'Business Health Dashboard'}
                </span>
                {report?.generated_at && (
                  <span style={{ fontSize: 11, color: 'var(--text3)', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 999 }}>
                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--emerald)' }} />
                    Updated {formatRelativeTime(report.generated_at)}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
        {report && report.pos_signals.revenue_trend_pct != null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--gold-dim)', border: '1px solid rgba(245,166,35,0.3)', borderRadius: 999, padding: '5px 13px', fontSize: 12, fontWeight: 500, color: 'var(--gold)', flexShrink: 0, marginTop: 2 }}>
            📊 POS Data Loaded
          </div>
        )}
      </div>

      {/* ── Tab content ────────────────────────────────── */}
      <div key={tab} style={{ padding: isMobile ? '16px 12px 60px' : '20px 24px 60px', animation: 'pageIn 0.35s cubic-bezier(0.22,1,0.36,1)' }}>
        {loading && <DashboardLoader />}

        {!loading && error && (
          <ErrorPage message={error} onRetry={() => { setLoading(true); setError(null); if (businessId) fetchAll(businessId); }} />
        )}

        {!loading && !error && report && (
          <>
            {tab === 'overview'    && <OverviewTab     report={report} ctx={actionsCtx} />}
            {tab === 'insights'    && <InsightsTab     report={report} ctx={actionsCtx} />}
            {tab === 'competitors' && (
              <CompetitorsTab
                report={report}
                businessId={businessId!}
                onAdded={(c) => setReport((r) => r ? { ...r, competitors: [c, ...r.competitors.filter((x) => x.place_id !== c.place_id)] } : r)}
                onRemoved={(pid) => setReport((r) => r ? { ...r, competitors: r.competitors.filter((x) => x.place_id !== pid) } : r)}
              />
            )}
            {tab === 'pos'         && <PosTab          businessId={report.business_id} />}
            {tab === 'history'     && <HistoryTab scores={histScores} error={histError} />}
            {tab === 'notes'       && <NotesTab        ctx={actionsCtx} />}
          </>
        )}
      </div>

      {toast && <Toast onClose={() => setToast(false)} />}
    </div>
  );
}

'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  generateReport, getHistory,
  type Band, type HealthReport, type HistoryEntry,
} from '@/lib/api';
import { useBusinessId } from '@/lib/business-context';
import { useAuth } from '@/lib/auth-context';
import { Bars, Gauge, Logo, ScoreBar, Skeleton, Stat, ThemeToggle } from '@/components/ui';

// ─── Static data (not yet available from API) ──────────────────────────────────
const STATIC_WEEKLY = [
  { week: 'W1', rev: 85000 }, { week: 'W2', rev: 92000 }, { week: 'W3', rev: 78000 },
  { week: 'W4', rev: 105000 }, { week: 'W5', rev: 98000 }, { week: 'W6', rev: 110000 },
  { week: 'W7', rev: 108000 }, { week: 'W8', rev: 115000 },
];
const STATIC_CATS = [
  { name: 'Dal Makhani',    rev: 38000, pct: 33, color: 'var(--gold)'    },
  { name: 'Paneer Dishes',  rev: 27000, pct: 23, color: 'var(--violet)'  },
  { name: 'Tandoori Items', rev: 23000, pct: 20, color: 'var(--emerald)' },
  { name: 'Breads & Rotis', rev: 14000, pct: 12, color: 'var(--red)'     },
  { name: 'Beverages',      rev: 13000, pct: 11, color: 'var(--yellow)'  },
];
const STATIC_REVIEWS = [
  { stars: 5, text: "Best dal makhani in KP! Perfectly creamy and the service was quick even during lunch hour.", author: 'Priya M.' },
  { stars: 4, text: "Great Punjabi food. Gets crowded at peak hours but the flavours make it worth the wait.", author: 'Aakash K.' },
  { stars: 5, text: "Authentic flavours, generous portions. The signature dal makhani is worth every rupee.", author: 'Sneha R.' },
];

// ─── Types ─────────────────────────────────────────────────────────────────────
type Tab         = 'overview' | 'insights' | 'competitors' | 'pos' | 'history';
type DisplayBand = 'green' | 'yellow' | 'red';

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview',    label: 'Overview'    },
  { id: 'insights',    label: 'Insights'    },
  { id: 'competitors', label: 'Competitors' },
  { id: 'pos',         label: 'POS'         },
  { id: 'history',     label: 'History'     },
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

function ActionBanner({ action }: { action: string }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(245,166,35,0.1), rgba(139,111,255,0.1))',
      border: '1px solid var(--border2)', borderRadius: 'var(--r2)',
      padding: '18px 20px', display: 'flex', alignItems: 'flex-start', gap: 14, marginTop: 16,
    }}>
      <div style={{ width: 36, height: 36, background: 'var(--gold)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width={14} height={18} viewBox="0 0 10 16" fill="black"><path d="M7 0L0 9h4.5L3 16 10 7H5.5L7 0z" /></svg>
      </div>
      <div style={{ flex: 1 }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text3)', display: 'block', marginBottom: 5 }}>
          This Week&apos;s Action
        </span>
        <p style={{ fontSize: 13, color: 'var(--text2)', margin: 0, lineHeight: 1.65 }}>{action}</p>
      </div>
      <button style={{ flexShrink: 0, padding: '8px 14px', background: 'var(--gold)', border: 'none', borderRadius: 8, color: '#000', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap' }}>
        Mark Done
      </button>
    </div>
  );
}

// ─── Loading skeleton ──────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr 1fr', gap: 16, alignItems: 'start' }}>
        {/* Col 1 */}
        <div style={CARD}>
          <Skeleton height={12} width="55%" style={{ marginBottom: 18, borderRadius: 4 }} />
          <Skeleton height={118} style={{ borderRadius: 'var(--r2)', marginBottom: 20 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[1, 2, 3].map((i) => (
              <div key={i}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Skeleton height={11} width="45%" style={{ borderRadius: 3 }} />
                  <Skeleton height={11} width="20%" style={{ borderRadius: 3 }} />
                </div>
                <Skeleton height={5} style={{ borderRadius: 999 }} />
              </div>
            ))}
          </div>
        </div>
        {/* Col 2 */}
        <div style={CARD}>
          <Skeleton height={12} width="50%" style={{ marginBottom: 18, borderRadius: 4 }} />
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <Skeleton height={72} style={{ flex: 1, borderRadius: 'var(--r)' }} />
            <Skeleton height={72} style={{ flex: 1, borderRadius: 'var(--r)' }} />
          </div>
          {[1, 2, 3].map((i) => <Skeleton key={i} height={70} style={{ borderRadius: 'var(--r)', marginBottom: 8 }} />)}
        </div>
        {/* Col 3 */}
        <div style={CARD}>
          <Skeleton height={12} width="45%" style={{ marginBottom: 18, borderRadius: 4 }} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={72} style={{ borderRadius: 'var(--r)' }} />)}
          </div>
          <Skeleton height={90} style={{ borderRadius: 'var(--r)' }} />
        </div>
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
function OverviewTab({ report }: { report: HealthReport }) {
  const band = mapBand(report.band);
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr 1fr', gap: 16, alignItems: 'start' }}>

        {/* Col 1 — Health Score */}
        <div style={CARD}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'radial-gradient(ellipse 120% 60% at 50% 0%, rgba(16,217,160,0.07), transparent 60%)', pointerEvents: 'none' }} />
          <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', gap: 18 }}>
            <span style={SEC}>Health Score</span>
            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <Gauge score={report.final_score} band={band} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <ScoreBar label="Review Score"     val={report.sub_scores.review_score}     weight={40} color="var(--violet)"  />
              <ScoreBar label="Competitor Score" val={report.sub_scores.competitor_score} weight={25} color="var(--gold)"    />
              <ScoreBar label="POS Score"        val={report.sub_scores.pos_score}        weight={35} color="var(--emerald)" />
            </div>
          </div>
        </div>

        {/* Col 2 — Google Presence */}
        <div style={CARD}>
          <span style={SEC}>Google Presence</span>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <Stat label="Rating"  value={`${report.google_rating}★`} sub="Area avg ~4.1★"  color="var(--gold)"   glow />
            <Stat label="Reviews" value={String(report.total_reviews)} sub="Google Places total" color="var(--violet)" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {report.reviews.filter((r) => r.text.trim()).length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No reviews available — add a Google Place ID to see real reviews.</p>
            ) : report.reviews.filter((r) => r.text.trim()).map((r, i) => (
              <div key={i} style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 'var(--r)', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <Stars n={r.rating} />
                  <span style={{ fontSize: 10, color: 'var(--text3)' }}>{r.relative_time}</span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text2)', margin: 0, lineHeight: 1.5 }}>{r.text || <em style={{ color: 'var(--text3)' }}>No text</em>}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Col 3 — POS Signals */}
        <div style={CARD}>
          <span style={SEC}>POS Signals</span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
            <Stat label="POS Score" value={String(report.sub_scores.pos_score)} sub="out of 100" color="var(--emerald)" glow />
            <Stat label="Top Product" value="Dal Makhani" sub="33% of revenue" color="var(--gold)" />
            <Stat label="AOV Direction" value="↑ Up" sub="₹428 avg order" color="var(--emerald)" />
            <div style={{ background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 'var(--r)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)' }}>Slow Items</span>
              {['Breads & Rotis', 'Beverages'].map((s) => (
                <span key={s} style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 11, color: 'var(--red)' }}>{s}</span>
              ))}
            </div>
          </div>
          <span style={{ ...SEC, marginBottom: 8 }}>8-Week Revenue</span>
          <Bars data={STATIC_WEEKLY} height={80} />
        </div>
      </div>

      <ActionBanner action={report.action} />
    </div>
  );
}

// ─── TAB: Insights ─────────────────────────────────────────────────────────────
function InsightsTab({ report }: { report: HealthReport }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 860 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 3px' }}>
            AI-Generated Insights
          </h2>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            Powered by Claude · Generated {new Date(report.generated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        </div>
        <div style={{ background: 'var(--violet-dim)', border: '1px solid var(--violet)', borderRadius: 999, padding: '3px 12px', fontSize: 11, fontWeight: 600, color: 'var(--violet)' }}>
          3 active insights
        </div>
      </div>

      {report.insights.map((text, i) => (
        <div key={i} style={{ ...CARD, display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ width: 30, height: 30, borderRadius: '50%', background: INSIGHT_DIMS[i], border: `1.5px solid ${INSIGHT_COLORS[i]}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13, color: INSIGHT_COLORS[i], flexShrink: 0 }}>
            {i + 1}
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 14, color: 'var(--text)', margin: '0 0 14px', lineHeight: 1.7 }}>{text}</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button style={GHOST_BTN}>Mark Actioned</button>
              <button style={GHOST_BTN}>Save to Notes</button>
            </div>
          </div>
        </div>
      ))}

      <ActionBanner action={report.action} />
    </div>
  );
}

// ─── TAB: Competitors ──────────────────────────────────────────────────────────
function CompetitorsTab({ report }: { report: HealthReport }) {
  const myRating    = report.google_rating;
  const competitors = report.competitors;
  const topThreat   = competitors.find((c) => c.rating > myRating);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      <div style={CARD}>
        <span style={SEC}>Nearby Competitors · 800m radius</span>
        {competitors.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>No nearby competitors found.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {competitors.map((c, i) => {
              const isThreat = c.rating > myRating;
              return (
                <div key={c.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px', borderRadius: 'var(--r)', background: isThreat ? 'rgba(255,95,95,0.05)' : 'transparent', border: `1px solid ${isThreat ? 'rgba(255,95,95,0.15)' : 'transparent'}` }}>
                  <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 11, color: 'var(--text3)', width: 22, flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}</span>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{c.name}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 6 }}>{c.review_count.toLocaleString()} reviews</span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 13, color: isThreat ? 'var(--red)' : 'var(--text2)' }}>{c.rating}★</span>
                  {isThreat && <span style={{ background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 4, padding: '1px 6px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--red)', textTransform: 'uppercase' }}>THREAT</span>}
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
            <span style={{ color: 'var(--red)', fontWeight: 600 }}>{topThreat.name}</span> at {topThreat.rating}★ is your highest-rated nearby competitor. A {(topThreat.rating - myRating).toFixed(1)}★ gap to close.
          </div>
        )}
      </div>
    </div>
  );
}

// ─── TAB: POS ──────────────────────────────────────────────────────────────────
function PosTab({ report }: { report: HealthReport }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
        <div style={CARD}>
          <span style={SEC}>Revenue by Category</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {STATIC_CATS.map((cat) => (
              <div key={cat.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: cat.color, flexShrink: 0, display: 'inline-block' }} />
                    <span style={{ fontSize: 13, color: 'var(--text2)' }}>{cat.name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 12, color: 'var(--text3)' }}>₹{(cat.rev / 1000).toFixed(0)}k</span>
                    <span style={{ fontFamily: 'var(--font-space-mono), monospace', fontSize: 12, fontWeight: 700, color: 'var(--text)', width: 30, textAlign: 'right' }}>{cat.pct}%</span>
                  </div>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: `${cat.pct}%`, height: '100%', background: cat.color, borderRadius: 999 }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={CARD}>
            <span style={SEC}>8-Week Revenue Trend</span>
            <Bars data={STATIC_WEEKLY} height={100} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Stat label="POS Score"    value={String(report.sub_scores.pos_score)} sub="out of 100"  color="var(--emerald)" glow />
            <Stat label="Latest Week"  value="₹1.15L"                              sub="est. Apr 21" color="var(--violet)"       />
          </div>
        </div>
      </div>

      <div style={{ ...CARD, display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px' }}>
        <span style={{ fontSize: 26, lineHeight: 1, flexShrink: 0 }}>🍽️</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 3 }}>Petpooja</div>
          <div style={{ fontSize: 12, color: 'var(--text3)' }}>Connected · Last sync 2 hours ago · 90 days loaded</div>
        </div>
        <div style={{ background: 'var(--emerald-dim)', border: '1px solid var(--emerald)', borderRadius: 999, padding: '3px 12px', fontSize: 11, fontWeight: 600, color: 'var(--emerald)', flexShrink: 0 }}>Active</div>
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

// ─── Dashboard Page ─────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router           = useRouter();
  const { businessId, bizLoading, clearBusinessId } = useBusinessId();
  const { user, loading: authLoading, signOut } = useAuth();

  const [report,       setReport]       = useState<HealthReport | null>(null);
  const [histScores,   setHistScores]   = useState<HistoryEntry[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [histError,    setHistError]    = useState<string | null>(null);
  const [refreshing,   setRefreshing]   = useState(false);
  const [toast,        setToast]        = useState(false);
  const [tab,          setTab]          = useState<Tab>('overview');
  const [hoveredTab,   setHoveredTab]   = useState<Tab | null>(null);
  const [menuOpen,     setMenuOpen]     = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const fetchAll = useCallback(async (id: string) => {
    try {
      const [rep, hist] = await Promise.allSettled([
        generateReport(id),
        getHistory(id, 12),
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
      const rep = await generateReport(businessId);
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
      <nav style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--nav-bg)', backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)', borderBottom: '1px solid var(--border)', height: 60, display: 'flex', alignItems: 'center', padding: '0 20px', gap: 12 }}>
        <Logo size={26} />

        <div style={{ display: 'flex', gap: 2, flex: 1, justifyContent: 'center' }}>
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              onMouseEnter={() => setHoveredTab(t.id)} onMouseLeave={() => setHoveredTab(null)}
              style={{ padding: '6px 14px', borderRadius: 8, border: 'none', background: tab === t.id ? 'rgba(255,255,255,0.08)' : 'transparent', color: tab === t.id ? 'var(--text)' : hoveredTab === t.id ? 'var(--text2)' : 'var(--text3)', fontWeight: tab === t.id ? 600 : 400, fontSize: 13, cursor: 'pointer', transition: 'background 150ms, color 150ms', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <ThemeToggle />
          <button onClick={handleRefresh} disabled={refreshing} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 11px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text2)', fontSize: 12, cursor: refreshing ? 'not-allowed' : 'pointer', fontFamily: 'inherit', opacity: refreshing ? 0.6 : 1, transition: 'opacity 150ms' }}>
            {refreshing ? <Spin size={12} /> : (
              <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
                <path d="M1 4v6h6" /><path d="M23 20v-6h-6" />
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15" />
              </svg>
            )}
            Refresh
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'var(--emerald-dim)', border: '1px solid rgba(16,217,160,0.25)', borderRadius: 999, padding: '4px 10px', fontSize: 11, fontWeight: 500, color: 'var(--emerald)' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--emerald)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block', flexShrink: 0 }} />
            Mon 8AM
          </div>
          {/* Avatar + dropdown */}
          <div ref={menuRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              style={{ width: 32, height: 32, borderRadius: '50%', background: 'linear-gradient(135deg, var(--violet), var(--gold))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 14, color: '#fff', flexShrink: 0, cursor: 'pointer', border: 'none' }}
            >
              {report?.business_name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? 'U'}
            </button>

            {menuOpen && (
              <div style={{
                position: 'absolute', top: 40, right: 0, width: 200,
                background: 'var(--bg2)', border: '1px solid var(--border2)',
                borderRadius: 'var(--r)', boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                overflow: 'hidden', zIndex: 300,
                animation: 'fadeUp 0.15s ease both',
              }}>
                {/* User info */}
                <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-space-grotesk), sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {user?.email}
                  </div>
                </div>

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
      <div style={{ padding: '20px 24px 0', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          {loading ? (
            <>
              <Skeleton height={22} width={200} style={{ marginBottom: 6, borderRadius: 6 }} />
              <Skeleton height={12} width={280} style={{ borderRadius: 4 }} />
            </>
          ) : (
            <>
              <h1 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 22, letterSpacing: '-0.02em', color: 'var(--text)', margin: '0 0 3px' }}>
                {report?.business_name ?? '—'}
              </h1>
              <span style={{ fontSize: 12, color: 'var(--text3)' }}>Business Health Dashboard</span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--gold-dim)', border: '1px solid rgba(245,166,35,0.3)', borderRadius: 999, padding: '5px 13px', fontSize: 12, fontWeight: 500, color: 'var(--gold)', flexShrink: 0, marginTop: 2 }}>
          🍽️ Petpooja Connected
        </div>
      </div>

      {/* ── Tab content ────────────────────────────────── */}
      <div key={tab} style={{ padding: '20px 24px 60px', animation: 'pageIn 0.35s cubic-bezier(0.22,1,0.36,1)' }}>
        {loading && <DashboardSkeleton />}

        {!loading && error && (
          <ErrorPage message={error} onRetry={() => { setLoading(true); setError(null); if (businessId) fetchAll(businessId); }} />
        )}

        {!loading && !error && report && (
          <>
            {tab === 'overview'    && <OverviewTab     report={report} />}
            {tab === 'insights'    && <InsightsTab     report={report} />}
            {tab === 'competitors' && <CompetitorsTab  report={report} />}
            {tab === 'pos'         && <PosTab          report={report} />}
            {tab === 'history'     && <HistoryTab scores={histScores} error={histError} />}
          </>
        )}
      </div>

      {toast && <Toast onClose={() => setToast(false)} />}
    </div>
  );
}

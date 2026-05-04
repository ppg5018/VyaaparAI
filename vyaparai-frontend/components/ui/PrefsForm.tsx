'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CompetitorPrefs, CompetitorPreview, getCompetitorPreview, savePreferences,
} from '@/lib/api';

const RADII: CompetitorPrefs['radius_m'][] = [500, 800, 1000, 1500, 2000];
const RADIUS_LABELS: Record<number, string> = {
  500: '500m', 800: '800m', 1000: '1km', 1500: '1.5km', 2000: '2km',
};

const REVIEW_STOPS = [0, 5, 20, 50, 100, 200, 500, 1000];

function valueToLog(val: number): number {
  let best = 0;
  for (let i = 0; i < REVIEW_STOPS.length; i++) {
    if (REVIEW_STOPS[i] <= val) best = i;
  }
  return best;
}

export interface PrefsFormProps {
  businessId: string;
  category: string;
  userId?: string;
  initialPrefs?: CompetitorPrefs | null;
  initialMode?: 'auto' | 'custom';
  onSaved?: (mode: 'auto' | 'custom') => void;
  onSkip?: () => void;
}

export default function PrefsForm({
  businessId, category, userId,
  initialPrefs, initialMode = 'auto', onSaved, onSkip,
}: PrefsFormProps) {
  const [mode, setMode]       = useState<'auto' | 'custom'>(initialMode);
  const [radius, setRadius]   = useState<CompetitorPrefs['radius_m']>(
    initialPrefs?.radius_m ?? 800,
  );
  const [minIdx, setMinIdx]   = useState(valueToLog(initialPrefs?.min_reviews ?? 0));
  const [maxIdx, setMaxIdx]   = useState(
    initialPrefs?.max_reviews == null
      ? REVIEW_STOPS.length - 1
      : valueToLog(initialPrefs.max_reviews),
  );
  const [subcats, setSubcats] = useState<string[]>(initialPrefs?.subcategories ?? []);
  const [preview, setPreview] = useState<CompetitorPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [saving, setSaving]   = useState(false);

  // Fetch preview on mount + on radius change (debounced).
  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const p = await getCompetitorPreview(businessId, radius);
        if (!cancelled) {
          setPreview(p);
          if (subcats.length === 0 && p.own_subcategory) setSubcats([p.own_subcategory]);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Preview failed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, radius]);

  const filteredCount = useMemo(() => {
    if (!preview) return 0;
    const min = REVIEW_STOPS[minIdx];
    return Object.entries(preview.review_buckets)
      .filter(([k]) => parseInt(k, 10) <= min || min === 0)
      .reduce((acc, [, v]) => Math.max(acc, v), 0);
  }, [preview, minIdx]);

  function toggleMode() {
    setMode((m) => (m === 'auto' ? 'custom' : 'auto'));
  }

  function toggleSubcat(tag: string) {
    setMode('custom');
    setSubcats((s) => (s.includes(tag) ? s.filter((t) => t !== tag) : [...s, tag]));
  }

  async function handleAuto() {
    if (!businessId) return;
    setSaving(true);
    try {
      await savePreferences(businessId, { mode: 'auto' }, userId);
      onSaved?.('auto');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (!businessId) return;
    setSaving(true);
    try {
      const max = maxIdx >= REVIEW_STOPS.length - 1 ? null : REVIEW_STOPS[maxIdx];
      await savePreferences(businessId, {
        mode: 'custom',
        prefs: {
          radius_m: radius,
          min_reviews: REVIEW_STOPS[minIdx],
          max_reviews: max,
          subcategories: subcats,
        },
      }, userId);
      onSaved?.('custom');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  const minLabel = REVIEW_STOPS[minIdx].toString();
  const maxLabel = maxIdx >= REVIEW_STOPS.length - 1 ? '∞' : REVIEW_STOPS[maxIdx].toString();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Hero CTA */}
      <div style={{
        padding: 20, border: '1.5px solid var(--border)', borderRadius: 12,
        background: 'var(--surface)',
      }}>
        <h3 style={{ margin: 0, marginBottom: 8 }}>Let Refloat decide</h3>
        <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 14 }}>
          We'll auto-pick competitors near you based on category similarity. You can change this later.
        </p>
        <button
          type="button"
          onClick={handleAuto}
          disabled={saving}
          style={{
            padding: '10px 18px', borderRadius: 8, border: 'none',
            background: 'var(--text)', color: 'var(--bg)', cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          {saving && mode === 'auto' ? 'Saving…' : 'Use auto'}
        </button>
        <button
          type="button"
          onClick={toggleMode}
          style={{
            marginLeft: 12, padding: '10px 18px', borderRadius: 8,
            border: '1.5px solid var(--border)', background: 'transparent',
            color: 'var(--text)', cursor: 'pointer',
          }}
        >
          {mode === 'auto' ? 'Or customize ↓' : 'Hide options ↑'}
        </button>
      </div>

      {mode === 'custom' && (
        <>
          {/* Sub-categories */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Compete against</h4>
            <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 13 }}>
              Pick the sub-categories you want benchmarked. Numbers show nearby places.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {preview && Object.entries(preview.subcategory_counts).map(([tag, count]) => {
                const active = subcats.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleSubcat(tag)}
                    style={{
                      padding: '6px 12px', borderRadius: 999, fontSize: 13,
                      border: active ? '1.5px solid var(--text)' : '1.5px solid var(--border)',
                      background: active ? 'var(--text)' : 'transparent',
                      color: active ? 'var(--bg)' : 'var(--text)', cursor: 'pointer',
                    }}
                  >
                    {tag.replace(/_/g, ' ')} ({count})
                  </button>
                );
              })}
              {!preview && <span style={{ color: 'var(--muted)' }}>Loading…</span>}
            </div>
          </section>

          {/* Distance */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Distance</h4>
            <div style={{ display: 'flex', gap: 8 }}>
              {RADII.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => { setMode('custom'); setRadius(r); }}
                  style={{
                    padding: '6px 14px', borderRadius: 8, fontSize: 13,
                    border: radius === r ? '1.5px solid var(--text)' : '1.5px solid var(--border)',
                    background: radius === r ? 'var(--text)' : 'transparent',
                    color: radius === r ? 'var(--bg)' : 'var(--text)', cursor: 'pointer',
                  }}
                >
                  {RADIUS_LABELS[r]}
                </button>
              ))}
            </div>
          </section>

          {/* Reviews range */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Review-count range</h4>
            <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 13 }}>
              Min: {minLabel} · Max: {maxLabel}{loading ? ' · loading…' : ''}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <input
                type="range" min={0} max={REVIEW_STOPS.length - 1} step={1}
                value={minIdx}
                onChange={(e) => { setMode('custom'); setMinIdx(Math.min(Number(e.target.value), maxIdx)); }}
                style={{ flex: 1 }}
              />
              <input
                type="range" min={0} max={REVIEW_STOPS.length - 1} step={1}
                value={maxIdx}
                onChange={(e) => { setMode('custom'); setMaxIdx(Math.max(Number(e.target.value), minIdx)); }}
                style={{ flex: 1 }}
              />
            </div>
            {preview && preview.top_examples.length > 0 && (
              <p style={{ marginTop: 10, fontSize: 13, color: 'var(--muted)' }}>
                Top nearby: {preview.top_examples.slice(0, 3).map((e) => `${e.name} (${e.review_count})`).join(', ')}
              </p>
            )}
            {preview && (
              <p style={{ marginTop: 4, fontSize: 12, color: 'var(--muted)' }}>
                Approx. matches in this range: {filteredCount}
              </p>
            )}
          </section>

          {/* Footer */}
          <div style={{ display: 'flex', gap: 12 }}>
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                style={{
                  padding: '10px 18px', borderRadius: 8,
                  border: '1.5px solid var(--border)', background: 'transparent',
                  color: 'var(--text)', cursor: 'pointer',
                }}
              >
                Skip for now
              </button>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '10px 18px', borderRadius: 8, border: 'none',
                background: 'var(--text)', color: 'var(--bg)', cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              {saving ? 'Saving…' : 'Save preferences'}
            </button>
          </div>
        </>
      )}

      {error && (
        <div role="alert" style={{ color: '#c33', fontSize: 13 }}>
          {error}
        </div>
      )}

      <span style={{ display: 'none' }}>{category}</span>
    </div>
  );
}

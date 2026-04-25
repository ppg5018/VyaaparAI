'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Aurora, Field, Logo, Steps, ThemeToggle } from '@/components/ui';
import { onboardBusiness, searchPlaces, uploadPOS, type PlaceSuggestion } from '@/lib/api';
import { useBusinessId } from '@/lib/business-context';
import { getPendingUpload, setPendingUpload } from '@/lib/pending-upload';

const CATEGORIES = [
  'Restaurant', 'Cafe', 'Retail', 'Grocery',
  'Pharmacy', 'Medical', 'Manufacturing', 'Distributor',
];

const SHARED_INPUT_STYLE: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  background: 'var(--surface)',
  border: '1.5px solid var(--border)',
  borderRadius: 'var(--r)',
  color: 'var(--text)',
  fontSize: 14,
  fontFamily: 'inherit',
  outline: 'none',
};

function Spinner({ dark = false }: { dark?: boolean }) {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite', flexShrink: 0 }}>
      <circle cx={8} cy={8} r={6} stroke={dark ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.25)'} strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke={dark ? '#000' : '#fff'} strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

function BusinessNameInput({
  value,
  onChange,
  onSelectSuggestion,
}: {
  value: string;
  onChange: (v: string) => void;
  onSelectSuggestion: (s: PlaceSuggestion) => void;
}) {
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [open, setOpen]               = useState(false);
  const [fetching, setFetching]       = useState(false);
  const [activeIdx, setActiveIdx]     = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    onChange(v);
    setActiveIdx(-1);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (v.length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setFetching(true);
      const results = await searchPlaces(v);
      setSuggestions(results);
      setOpen(results.length > 0);
      setFetching(false);
    }, 320);
  };

  const handleSelect = (s: PlaceSuggestion) => {
    onSelectSuggestion(s);
    setSuggestions([]);
    setOpen(false);
    setActiveIdx(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      handleSelect(suggestions[activeIdx]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      {/* Label */}
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text2)', marginBottom: 6 }}>
        Business name <span style={{ color: 'var(--gold)' }}>*</span>
      </label>

      {/* Input row */}
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          value={value}
          placeholder="Sharma's Kitchen"
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          autoComplete="off"
          style={{
            ...SHARED_INPUT_STYLE,
            paddingRight: 36,
            borderColor: open ? 'var(--gold)' : 'var(--border)',
            transition: 'border-color 150ms',
          }}
        />
        {/* Spinner / search icon */}
        <span style={{
          position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
          display: 'flex', alignItems: 'center', pointerEvents: 'none',
        }}>
          {fetching ? (
            <Spinner dark={false} />
          ) : (
            <svg width={14} height={14} viewBox="0 0 16 16" fill="none">
              <circle cx={7} cy={7} r={5} stroke="var(--text3)" strokeWidth={1.5} />
              <path d="M11 11l3 3" stroke="var(--text3)" strokeWidth={1.5} strokeLinecap="round" />
            </svg>
          )}
        </span>
      </div>

      {/* Hint */}
      <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 5, marginBottom: 0 }}>
        Start typing to search Google — select a result to auto-fill
      </p>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% - 6px)',
          left: 0, right: 0,
          background: 'var(--bg2)',
          border: '1.5px solid var(--border2)',
          borderRadius: 'var(--r)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
          zIndex: 200,
          overflow: 'hidden',
        }}>
          {suggestions.map((s, i) => (
            <button
              key={s.place_id}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); handleSelect(s); }}
              style={{
                width: '100%',
                padding: '10px 14px',
                background: i === activeIdx ? 'var(--gold-dim)' : 'transparent',
                border: 'none',
                borderBottom: i < suggestions.length - 1 ? '1px solid var(--border)' : 'none',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
                transition: 'background 100ms',
              }}
              onMouseEnter={() => setActiveIdx(i)}
              onMouseLeave={() => setActiveIdx(-1)}
            >
              <span style={{
                fontSize: 13, fontWeight: 600,
                color: i === activeIdx ? 'var(--gold)' : 'var(--text)',
                fontFamily: 'var(--font-space-grotesk), sans-serif',
              }}>
                {s.name}
              </span>
              {s.address && (
                <span style={{ fontSize: 11, color: 'var(--text3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.address}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BusinessPage() {
  const router             = useRouter();
  const searchParams       = useSearchParams();
  const cameFromConnections = searchParams.get('from') === 'connections';
  const { setBusinessId }  = useBusinessId();

  const [businessName, setBusinessName] = useState('');
  const [ownerName, setOwnerName]       = useState('');
  const [category, setCategory]         = useState('');
  const [placeId, setPlaceId]           = useState('');
  const [placeVerified, setPlaceVerified] = useState(false);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState('');

  const handleSelectSuggestion = (s: PlaceSuggestion) => {
    setBusinessName(s.name);
    setPlaceId(s.place_id);
    setPlaceVerified(true);
  };

  const handleNameChange = (v: string) => {
    setBusinessName(v);
    if (placeVerified) {
      setPlaceId('');
      setPlaceVerified(false);
    }
  };

  const handleSubmit = async () => {
    if (!businessName || !ownerName || !category) {
      setError('Please fill in all required fields.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const result = await onboardBusiness({
        name:       businessName,
        ...(placeId && { place_id: placeId }),
        category,
        owner_name: ownerName,
      });
      setBusinessId(result.business_id);

      const pendingFile = getPendingUpload();
      if (pendingFile) {
        setPendingUpload(null);
        try { await uploadPOS(result.business_id, pendingFile); } catch { /* non-fatal */ }
      }

      router.push(cameFromConnections ? '/profile/connections' : '/dashboard');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Setup failed. Please try again.';
      setError(msg);
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column' }}>
      <Aurora />

      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'var(--nav-bg)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)', height: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
      }}>
        <Logo size={26} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {cameFromConnections && (
            <button
              type="button"
              onClick={() => router.push('/profile/connections')}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', borderRadius: 8,
                background: 'transparent', border: '1px solid var(--border)',
                color: 'var(--text2)', fontSize: 13, fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
                <line x1={19} y1={12} x2={5} y2={12} /><polyline points="12 19 5 12 12 5" />
              </svg>
              Back to Connections
            </button>
          )}
          <ThemeToggle />
        </div>
      </nav>

      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '40px 24px 60px', position: 'relative', zIndex: 1 }}>
        <div style={{
          width: '100%', maxWidth: 480,
          display: 'flex', flexDirection: 'column', gap: 32,
          animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both',
        }}>
          {cameFromConnections ? (
            <button
              type="button"
              onClick={() => router.push('/profile/connections')}
              style={{
                alignSelf: 'flex-start',
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', marginBottom: -8,
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--text2)', fontSize: 12, fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              <svg width={11} height={11} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
                <line x1={19} y1={12} x2={5} y2={12} /><polyline points="12 19 5 12 12 5" />
              </svg>
              Cancel & return to Connections
            </button>
          ) : (
            <Steps active={2} />
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <h1 style={{
              fontFamily: 'var(--font-space-grotesk), sans-serif',
              fontWeight: 700, fontSize: 26, letterSpacing: '-0.03em',
              color: 'var(--text)', margin: 0,
            }}>
              {cameFromConnections ? 'Update your business details' : 'Tell us about your business'}
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
              We&apos;ll use this to pull your Google Reviews and find competitors nearby.
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Autocomplete business name */}
            <BusinessNameInput
              value={businessName}
              onChange={handleNameChange}
              onSelectSuggestion={handleSelectSuggestion}
            />

            {/* Verified badge or manual Place ID field */}
            {placeVerified ? (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '9px 14px',
                background: 'var(--emerald-dim)', border: '1px solid var(--emerald)',
                borderRadius: 'var(--r)', fontSize: 12,
              }}>
                <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
                  <circle cx={7} cy={7} r={6} fill="var(--emerald)" />
                  <path d="M4 7l2 2 4-4" stroke="#000" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span style={{ color: 'var(--emerald)', fontWeight: 500 }}>Google verified</span>
                <span style={{ color: 'var(--text3)', marginLeft: 4, fontFamily: 'var(--font-space-mono)', fontSize: 11 }}>
                  {placeId.slice(0, 18)}…
                </span>
                <button
                  type="button"
                  onClick={() => { setPlaceId(''); setPlaceVerified(false); }}
                  style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text3)', cursor: 'pointer', fontSize: 12 }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <Field
                label="Google Place ID (optional)"
                value={placeId}
                onChange={setPlaceId}
                placeholder="ChIJ… — or leave blank to auto-detect"
              />
            )}

            <Field label="Owner name" value={ownerName} onChange={setOwnerName} placeholder="Rajesh Sharma" req />
            <Field label="Category" type="select" value={category} onChange={setCategory} placeholder="Select a category" options={CATEGORIES} req />
          </div>

          {error && (
            <div style={{
              padding: '10px 14px',
              background: 'var(--red-dim)', border: '1px solid var(--red)',
              borderRadius: 'var(--r)', fontSize: 13, color: 'var(--red)',
            }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading}
              style={{
                maxWidth: 400, width: '100%', alignSelf: 'center',
                padding: '13px 20px',
                background: loading ? 'var(--gold-dim)' : 'var(--gold)',
                border: 'none', borderRadius: 'var(--r)',
                color: '#000', fontFamily: 'var(--font-space-grotesk), sans-serif',
                fontWeight: 700, fontSize: 15,
                cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                transition: 'background 150ms, opacity 150ms',
                opacity: loading ? 0.75 : 1,
              }}
            >
              {loading ? <><Spinner dark />&nbsp;Setting up your business…</> : 'Complete Setup'}
            </button>
            <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text3)', margin: 0, lineHeight: 1.5 }}>
              Your data is only used to generate your health score.{' '}
              <span style={{ color: 'var(--text2)' }}>We never post on your behalf.</span>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

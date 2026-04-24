'use client';

import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Aurora, Logo, Steps, ThemeToggle } from '@/components/ui';
import { setPendingUpload } from '@/lib/pending-upload';

const POS_INTEGRATIONS = [
  { id: 'petpooja',  name: 'Petpooja',         desc: 'Restaurant POS',       status: 'live' },
  { id: 'bharatpe',  name: 'BharatPe',          desc: 'Payment terminal',     status: 'live' },
  { id: 'tally',     name: 'Tally',             desc: 'Accounting & billing', status: 'soon' },
  { id: 'razorpay',  name: 'Razorpay POS',      desc: 'Card & UPI payments',  status: 'soon' },
  { id: 'phonepe',   name: 'PhonePe Business',  desc: 'UPI & settlements',    status: 'soon' },
  { id: 'shopify',   name: 'Shopify',           desc: 'E-commerce store',     status: 'soon' },
] as const;

type PosId = typeof POS_INTEGRATIONS[number]['id'];

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite', flexShrink: 0 }}>
      <circle cx={8} cy={8} r={6} stroke="rgba(0,0,0,0.2)" strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="#000" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

function PosLogo({ id }: { id: string }) {
  const logos: Record<string, React.ReactNode> = {
    petpooja: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#FF6B35" />
        <path d="M8 20V10c0-1.1.9-2 2-2h3c2.2 0 4 1.8 4 4s-1.8 4-4 4H10v4H8z" fill="#fff" />
        <circle cx={20} cy={18} r={3} fill="#fff" opacity={0.9} />
      </svg>
    ),
    bharatpe: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#00B9F1" />
        <text x={4} y={20} fontSize={11} fontWeight={700} fill="#fff" fontFamily="sans-serif">B₹</text>
      </svg>
    ),
    tally: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#0066CC" />
        <text x={5} y={20} fontSize={12} fontWeight={700} fill="#fff" fontFamily="sans-serif">T</text>
      </svg>
    ),
    razorpay: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#072654" />
        <path d="M9 20l4-12 6 7-3 1 2 4H9z" fill="#3395FF" />
      </svg>
    ),
    phonepe: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#5F259F" />
        <text x={6} y={20} fontSize={12} fontWeight={700} fill="#fff" fontFamily="sans-serif">₱</text>
      </svg>
    ),
    shopify: (
      <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
        <rect width={28} height={28} rx={8} fill="#96BF48" />
        <text x={6} y={20} fontSize={13} fontWeight={700} fill="#fff" fontFamily="sans-serif">S</text>
      </svg>
    ),
  };
  return <>{logos[id] ?? null}</>;
}

export default function PosPage() {
  const router = useRouter();

  const [selected, setSelected]       = useState<PosId | 'csv' | null>(null);
  const [connecting, setConnecting]   = useState(false);
  const [connected, setConnected]     = useState<PosId | null>(null);
  const [csvFile, setCsvFile]         = useState<File | null>(null);
  const [dragging, setDragging]       = useState(false);
  const timerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleSelectPos = (id: PosId, status: string) => {
    if (status === 'soon') return;
    if (timerRef.current) clearTimeout(timerRef.current);
    setSelected(id);
    setConnecting(true);
    setConnected(null);
    timerRef.current = setTimeout(() => {
      setConnecting(false);
      setConnected(id);
    }, 1200);
  };

  const handleFile = (file: File) => {
    if (!file.name.endsWith('.csv')) return;
    setCsvFile(file);
    setSelected('csv');
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, []);

  const canContinue =
    (selected === 'csv' && csvFile !== null) ||
    (selected !== null && selected !== 'csv' && connected === selected);

  const handleContinue = () => {
    if (!canContinue) return;
    if (selected === 'csv' && csvFile) {
      setPendingUpload(csvFile);
    } else {
      setPendingUpload(null);
    }
    router.push('/onboard/business');
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column' }}>
      <Aurora />

      {/* Nav */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'var(--nav-bg)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)', height: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
      }}>
        <Logo size={26} />
        <ThemeToggle />
      </nav>

      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '40px 24px 60px', position: 'relative', zIndex: 1 }}>
        <div style={{
          width: '100%', maxWidth: 580,
          display: 'flex', flexDirection: 'column', gap: 32,
          animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both',
        }}>
          <Steps active={1} />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <h1 style={{
              fontFamily: 'var(--font-space-grotesk), sans-serif',
              fontWeight: 700, fontSize: 26, letterSpacing: '-0.03em',
              color: 'var(--text)', margin: 0,
            }}>
              Connect your POS
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
              We&apos;ll use this to track your sales trends and spot slow categories.
            </p>
          </div>

          {/* POS grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            {POS_INTEGRATIONS.map((pos) => {
              const isSelected  = selected === pos.id;
              const isConnected = connected === pos.id;
              const isConnecting = connecting && selected === pos.id;
              const isSoon = pos.status === 'soon';

              return (
                <button
                  key={pos.id}
                  type="button"
                  onClick={() => handleSelectPos(pos.id, pos.status)}
                  disabled={isSoon}
                  style={{
                    background: isSelected ? 'var(--gold-dim)' : 'var(--surface)',
                    border: `1.5px solid ${isSelected ? 'var(--gold)' : 'var(--border)'}`,
                    borderRadius: 'var(--r2)',
                    padding: '16px 14px',
                    cursor: isSoon ? 'default' : 'pointer',
                    position: 'relative',
                    textAlign: 'left',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    opacity: isSoon ? 0.5 : 1,
                    transition: 'background 150ms, border-color 150ms, opacity 150ms',
                  }}
                >
                  {/* Coming soon badge */}
                  {isSoon && (
                    <span style={{
                      position: 'absolute', top: 8, right: 8,
                      fontSize: 9, fontWeight: 600, letterSpacing: '0.05em',
                      padding: '2px 6px', borderRadius: 999,
                      background: 'var(--surface2)', color: 'var(--text3)',
                      border: '1px solid var(--border)',
                    }}>
                      SOON
                    </span>
                  )}

                  {/* Connected badge */}
                  {isSelected && !isSoon && (
                    <span style={{
                      position: 'absolute', top: 8, right: 8,
                      fontSize: 9, fontWeight: 600, letterSpacing: '0.04em',
                      padding: '2px 7px', borderRadius: 999,
                      background: isConnected ? 'var(--emerald-dim)' : 'var(--gold-dim)',
                      color: isConnected ? 'var(--emerald)' : 'var(--gold)',
                      border: `1px solid ${isConnected ? 'var(--emerald)' : 'var(--gold)'}`,
                      display: 'flex', alignItems: 'center', gap: 4,
                    }}>
                      {isConnecting ? <><Spinner size={8} />…</> : '✓ Connected'}
                    </span>
                  )}

                  <PosLogo id={pos.id} />

                  <div>
                    <div style={{
                      fontFamily: 'var(--font-space-grotesk), sans-serif',
                      fontWeight: 700, fontSize: 13, color: 'var(--text)', marginBottom: 2,
                    }}>
                      {pos.name}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                      {pos.desc}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span style={{ fontSize: 12, color: 'var(--text3)', flexShrink: 0 }}>or upload manually</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          {/* CSV Upload */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInput.current?.click()}
            style={{
              border: `2px dashed ${dragging ? 'var(--gold)' : selected === 'csv' ? 'var(--emerald)' : 'var(--border2)'}`,
              borderRadius: 'var(--r2)',
              padding: '28px 24px',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 10,
              background: dragging ? 'var(--gold-dim)' : selected === 'csv' ? 'var(--emerald-dim)' : 'var(--surface)',
              transition: 'background 150ms, border-color 150ms',
              textAlign: 'center',
            }}
          >
            <input
              ref={fileInput}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />

            {selected === 'csv' && csvFile ? (
              <>
                <svg width={32} height={32} viewBox="0 0 32 32" fill="none">
                  <rect width={32} height={32} rx={8} fill="var(--emerald-dim)" />
                  <path d="M10 17l4 4 8-8" stroke="var(--emerald)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--emerald)', fontFamily: 'var(--font-space-grotesk), sans-serif' }}>
                    {csvFile.name}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>
                    {(csvFile.size / 1024).toFixed(1)} KB · Click to replace
                  </div>
                </div>
              </>
            ) : (
              <>
                <svg width={32} height={32} viewBox="0 0 32 32" fill="none">
                  <rect width={32} height={32} rx={8} fill="var(--surface2)" />
                  <path d="M16 10v10M11 15l5-5 5 5" stroke="var(--text3)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M10 22h12" stroke="var(--text3)" strokeWidth={2} strokeLinecap="round" />
                </svg>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text2)', fontFamily: 'var(--font-space-grotesk), sans-serif' }}>
                    Upload sales CSV
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>
                    Drag & drop or click to browse · .csv files only
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Skip */}
          <button
            type="button"
            onClick={() => { setSelected(null); setCsvFile(null); router.push('/onboard/business'); }}
            style={{
              background: 'none', border: 'none',
              fontSize: 13, color: 'var(--text3)',
              cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: 3,
              alignSelf: 'center', padding: '4px 8px',
            }}
          >
            Skip for now
          </button>

          {/* Continue */}
          <button
            type="button"
            onClick={handleContinue}
            disabled={!canContinue}
            style={{
              maxWidth: 400, width: '100%', alignSelf: 'center',
              padding: '13px 20px',
              background: canContinue ? 'var(--gold)' : 'var(--surface2)',
              border: 'none', borderRadius: 'var(--r)',
              color: canContinue ? '#000' : 'var(--text3)',
              fontFamily: 'var(--font-space-grotesk), sans-serif',
              fontWeight: 700, fontSize: 15,
              cursor: canContinue ? 'pointer' : 'not-allowed',
              transition: 'background 200ms, color 200ms',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
          >
            {connecting ? <><Spinner size={14} />Connecting…</> : 'Continue'}
          </button>
        </div>
      </main>
    </div>
  );
}

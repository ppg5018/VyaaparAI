'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Field } from '@/components/ui';
import { useAuth } from '@/lib/auth-context';

function Spinner() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite' }}>
      <circle cx={8} cy={8} r={6} stroke="rgba(0,0,0,0.25)" strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="#000" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

export default function ForgotPasswordPage() {
  const { resetPassword } = useAuth();

  const [email, setEmail]   = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');
  const [sent, setSent]     = useState(false);

  const handleSubmit = async () => {
    if (!email) {
      setError('Please enter your email address.');
      return;
    }
    setLoading(true);
    setError('');

    const { error: err } = await resetPassword(email);
    setLoading(false);

    if (err) {
      setError(err);
      return;
    }
    setSent(true);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h1 style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em',
          color: 'var(--text)', margin: 0, lineHeight: 1.2,
        }}>
          Reset password
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
          {sent
            ? 'Check your email for a reset link.'
            : 'Enter your email and we\'ll send you a reset link.'}
        </p>
      </div>

      {!sent && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Field label="Email address" type="email" value={email} onChange={setEmail} placeholder="you@example.com" req />
          </div>

          {error && (
            <div style={{
              padding: '10px 14px', background: 'var(--red-dim)',
              border: '1px solid var(--red)', borderRadius: 'var(--r)',
              fontSize: 13, color: 'var(--red)', marginTop: -12,
            }}>
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            style={{
              width: '100%', padding: '13px 20px',
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
            {loading ? <><Spinner />Sending…</> : 'Send reset link'}
          </button>
        </>
      )}

      {sent && (
        <div style={{
          padding: '14px 16px', background: 'var(--emerald-dim)',
          border: '1px solid var(--emerald)', borderRadius: 'var(--r)',
          fontSize: 13, color: 'var(--text)', lineHeight: 1.6,
        }}>
          We&apos;ve sent a password reset link to <strong>{email}</strong>. Click the link in your inbox to set a new password. The link expires in 1 hour.
        </div>
      )}

      <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text2)', margin: 0 }}>
        Remember your password?{' '}
        <Link href="/login" style={{ color: 'var(--gold)', textDecoration: 'none', fontWeight: 500 }}>
          Sign in
        </Link>
      </p>
    </div>
  );
}

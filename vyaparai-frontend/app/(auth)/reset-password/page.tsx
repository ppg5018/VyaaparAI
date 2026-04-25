'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Field } from '@/components/ui';
import { useAuth } from '@/lib/auth-context';
import { supabase } from '@/lib/supabase';

function Spinner() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite' }}>
      <circle cx={8} cy={8} r={6} stroke="rgba(0,0,0,0.25)" strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="#000" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

export default function ResetPasswordPage() {
  const router = useRouter();
  const { updatePassword } = useAuth();

  const [recoveryReady, setRecoveryReady] = useState(false);
  const [password, setPassword]           = useState('');
  const [confirm, setConfirm]             = useState('');
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState('');
  const [done, setDone]                   = useState(false);

  // Wait for the PASSWORD_RECOVERY event triggered by the URL hash.
  useEffect(() => {
    const { data: listener } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'PASSWORD_RECOVERY') setRecoveryReady(true);
    });
    // If the hash already parsed before our listener attached, getSession will have user.
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setRecoveryReady(true);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  const handleSubmit = async () => {
    if (!password || !confirm) {
      setError('Please fill in both fields.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    setError('');

    const { error: err } = await updatePassword(password);
    setLoading(false);

    if (err) {
      setError(err);
      return;
    }
    setDone(true);
    setTimeout(() => router.push('/login'), 2500);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h1 style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em',
          color: 'var(--text)', margin: 0, lineHeight: 1.2,
        }}>
          Set new password
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
          {done
            ? 'Password updated. Redirecting to sign in…'
            : 'Choose a strong password you haven\'t used before.'}
        </p>
      </div>

      {!recoveryReady && !done && (
        <div style={{
          padding: '10px 14px', background: 'var(--gold-dim)',
          border: '1px solid var(--gold)', borderRadius: 'var(--r)',
          fontSize: 13, color: 'var(--text2)',
        }}>
          Verifying reset link… If this hangs, the link may have expired. Request a new one from the{' '}
          <Link href="/forgot-password" style={{ color: 'var(--gold)', fontWeight: 500 }}>forgot password</Link> page.
        </div>
      )}

      {recoveryReady && !done && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Field label="New password"     type="password" value={password} onChange={setPassword} placeholder="At least 6 characters" req />
            <Field label="Confirm password" type="password" value={confirm}  onChange={setConfirm}  placeholder="Re-enter password"     req />
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
            {loading ? <><Spinner />Updating…</> : 'Update password'}
          </button>
        </>
      )}

      {done && (
        <div style={{
          padding: '14px 16px', background: 'var(--emerald-dim)',
          border: '1px solid var(--emerald)', borderRadius: 'var(--r)',
          fontSize: 13, color: 'var(--text)', lineHeight: 1.6,
        }}>
          Your password has been updated. Redirecting you to sign in…
        </div>
      )}
    </div>
  );
}

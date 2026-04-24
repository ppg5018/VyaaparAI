'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
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

export default function LoginPage() {
  const router       = useRouter();
  const { signIn }   = useAuth();

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const handleSubmit = async () => {
    if (!email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    setLoading(true);
    setError('');

    const { error: err, userId } = await signIn(email, password);
    if (err) {
      setError(err);
      setLoading(false);
      return;
    }
    // Check if this user has already onboarded on this device
    const hasBusinessId = userId
      ? !!localStorage.getItem(`vyapaar-business-id-${userId}`)
      : false;
    router.push(hasBusinessId ? '/dashboard' : '/onboard/pos');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h1 style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em',
          color: 'var(--text)', margin: 0, lineHeight: 1.2,
        }}>
          Welcome back
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
          Sign in to your VyaparAI account
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Field label="Email address" type="email" value={email} onChange={setEmail} placeholder="you@example.com" req />
        <Field label="Password" type="password" value={password} onChange={setPassword} placeholder="Enter your password" req />
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

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
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
          {loading ? <><Spinner />Signing in…</> : 'Sign In'}
        </button>

        <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text2)', margin: 0 }}>
          Don&apos;t have an account?{' '}
          <Link href="/signup" style={{ color: 'var(--gold)', textDecoration: 'none', fontWeight: 500 }}>
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}

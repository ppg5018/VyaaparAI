'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Field } from '@/components/ui';
import { useAuth } from '@/lib/auth-context';
import { getBusinessByUser } from '@/lib/api';

function Spinner() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none"
      style={{ animation: 'spin 0.75s linear infinite' }}>
      <circle cx={8} cy={8} r={6} stroke="rgba(0,0,0,0.25)" strokeWidth={2} />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="#000" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width={18} height={18} viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4" />
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
      <path d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.038l3.007-2.332z" fill="#FBBC05" />
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962L3.964 7.294C4.672 5.167 6.656 3.58 9 3.58z" fill="#EA4335" />
    </svg>
  );
}

export default function LoginPage() {
  const router       = useRouter();
  const { signIn, signInWithGoogle } = useAuth();

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError]       = useState('');

  const handleGoogle = async () => {
    if (googleLoading) return;
    setGoogleLoading(true);
    setError('');
    const { error: err } = await signInWithGoogle();
    if (err) {
      setError(err);
      setGoogleLoading(false);
    }
    // On success, browser navigates to Google → /auth/callback handles the rest.
  };

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
    // Check backend (source of truth) — fall back to localStorage for legacy rows with NULL user_id
    let hasBusinessId = false;
    if (userId) {
      const biz = await getBusinessByUser(userId);
      if (biz) {
        localStorage.setItem(`vyapaar-business-id-${userId}`, biz.business_id);
        hasBusinessId = true;
      } else {
        hasBusinessId = !!localStorage.getItem(`vyapaar-business-id-${userId}`);
      }
    }
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
          Sign in to your Refloat account
        </p>
      </div>

      {/* Google sign-in */}
      <button
        type="button"
        onClick={handleGoogle}
        disabled={googleLoading || loading}
        style={{
          width: '100%', padding: '12px 18px',
          background: 'var(--surface)', border: '1px solid var(--border2)',
          borderRadius: 'var(--r)', color: 'var(--text)',
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 600, fontSize: 14,
          cursor: googleLoading ? 'not-allowed' : 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
          transition: 'background 150ms, opacity 150ms',
          opacity: googleLoading ? 0.7 : 1,
        }}
      >
        {googleLoading ? <Spinner /> : <GoogleIcon />}
        {googleLoading ? 'Redirecting…' : 'Continue with Google'}
      </button>

      {/* Divider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        <span style={{ fontSize: 11, color: 'var(--text3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>or</span>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Field label="Email address" type="email" value={email} onChange={setEmail} placeholder="you@example.com" req />
        <Field label="Password" type="password" value={password} onChange={setPassword} placeholder="Enter your password" req />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: -8 }}>
          <Link href="/forgot-password" style={{ fontSize: 12, color: 'var(--gold)', textDecoration: 'none', fontWeight: 500 }}>
            Forgot password?
          </Link>
        </div>
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

        <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text3)', margin: 0, lineHeight: 1.6 }}>
          By signing in you agree to our{' '}
          <Link href="/terms" style={{ color: 'var(--text3)', textDecoration: 'underline' }}>Terms of Service</Link>
          {' '}and{' '}
          <Link href="/privacy" style={{ color: 'var(--text3)', textDecoration: 'underline' }}>Privacy Policy</Link>
        </p>
      </div>
    </div>
  );
}

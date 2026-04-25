'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Field, Steps } from '@/components/ui';
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

export default function SignupPage() {
  const router     = useRouter();
  const { signUp, signInWithGoogle } = useAuth();

  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [phone, setPhone]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError]       = useState('');
  const [confirmed, setConfirmed] = useState(false);

  const handleGoogle = async () => {
    if (googleLoading) return;
    setGoogleLoading(true);
    setError('');
    const { error: err } = await signInWithGoogle();
    if (err) {
      setError(err);
      setGoogleLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!name || !email || !phone || !password) {
      setError('Please fill in all fields.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setLoading(true);
    setError('');

    const { error: err, needsConfirmation } = await signUp(email, password, name, phone);
    if (err) {
      setError(err);
      setLoading(false);
      return;
    }
    if (needsConfirmation) {
      setConfirmed(true);
      setLoading(false);
      return;
    }
    router.push('/onboard/pos');
  };

  if (confirmed) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 20, textAlign: 'center',
        animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both',
      }}>
        <div style={{
          width: 56, height: 56, borderRadius: '50%',
          background: 'var(--emerald-dim)', border: '2px solid var(--emerald)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width={24} height={24} viewBox="0 0 24 24" fill="none">
            <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z" stroke="var(--emerald)" strokeWidth={1.5} />
            <path d="M2 8l10 7 10-7" stroke="var(--emerald)" strokeWidth={1.5} strokeLinecap="round" />
          </svg>
        </div>
        <div>
          <h2 style={{ fontFamily: 'var(--font-space-grotesk)', fontWeight: 700, fontSize: 22, color: 'var(--text)', margin: '0 0 8px' }}>
            Check your email
          </h2>
          <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0, lineHeight: 1.6 }}>
            We sent a confirmation link to <strong style={{ color: 'var(--text)' }}>{email}</strong>.
            <br />Click it to activate your account, then sign in.
          </p>
        </div>
        <Link href="/login" style={{
          padding: '11px 28px', background: 'var(--gold)',
          borderRadius: 'var(--r)', color: '#000',
          fontFamily: 'var(--font-space-grotesk)', fontWeight: 700, fontSize: 14,
          textDecoration: 'none',
        }}>
          Go to Sign In
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, animation: 'pageIn 0.45s cubic-bezier(0.22,1,0.36,1) both' }}>
      <Steps active={0} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h1 style={{
          fontFamily: 'var(--font-space-grotesk), sans-serif',
          fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em',
          color: 'var(--text)', margin: 0, lineHeight: 1.2,
        }}>
          Create your account
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
          Start monitoring your business health
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

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        <span style={{ fontSize: 11, color: 'var(--text3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>or use email</span>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Field label="Full name" value={name} onChange={setName} placeholder="Ramesh Sharma" req />
        <Field label="Email address" type="email" value={email} onChange={setEmail} placeholder="you@example.com" req />
        <Field label="Phone number" type="tel" value={phone} onChange={setPhone} placeholder="+91 98765 43210" req />
        <Field label="Password" type="password" value={password} onChange={setPassword} placeholder="Min. 6 characters" hint="Use a mix of letters, numbers, and symbols." req />
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
          {loading ? <><Spinner />Creating account…</> : 'Create Account'}
        </button>

        <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text2)', margin: 0 }}>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--gold)', textDecoration: 'none', fontWeight: 500 }}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

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

export default function SignupPage() {
  const router     = useRouter();
  const { signUp } = useAuth();

  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [phone, setPhone]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');
  const [confirmed, setConfirmed] = useState(false);

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

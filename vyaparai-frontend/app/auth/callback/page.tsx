'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabase';

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const finalize = async () => {
      try {
        // Supabase JS auto-exchanges the URL ?code=... for a session on load.
        // We just need to wait until the session is established, then route.
        const { data, error: sessErr } = await supabase.auth.getSession();
        if (sessErr) {
          setError(sessErr.message);
          return;
        }

        const userId = data.session?.user?.id;
        if (!userId) {
          // Listen briefly in case the session lands a moment later
          const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
            if (session?.user?.id) {
              listener.subscription.unsubscribe();
              const hasBiz = !!localStorage.getItem(`vyapaar-business-id-${session.user.id}`);
              router.replace(hasBiz ? '/dashboard' : '/onboard/pos');
            }
          });
          // Hard timeout fallback
          setTimeout(() => {
            listener.subscription.unsubscribe();
            setError('Sign-in took too long. Please try again.');
          }, 8000);
          return;
        }

        const hasBiz = !!localStorage.getItem(`vyapaar-business-id-${userId}`);
        router.replace(hasBiz ? '/dashboard' : '/onboard/pos');
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Sign-in failed.');
      }
    };
    finalize();
  }, [router]);

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
        {!error && (
          <>
            <svg width={36} height={36} viewBox="0 0 36 36" fill="none" style={{ animation: 'spin 0.85s linear infinite' }}>
              <circle cx={18} cy={18} r={14} stroke="var(--border2)" strokeWidth={3} />
              <path d="M18 4a14 14 0 0 1 14 14" stroke="var(--gold)" strokeWidth={3} strokeLinecap="round" />
            </svg>
            <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>Signing you in…</p>
          </>
        )}
        {error && (
          <>
            <div style={{
              padding: '14px 18px', background: 'var(--red-dim)',
              border: '1px solid var(--red)', borderRadius: 'var(--r)',
              fontSize: 13, color: 'var(--red)', maxWidth: 360,
            }}>
              {error}
            </div>
            <button
              onClick={() => router.replace('/login')}
              style={{
                padding: '10px 22px', background: 'var(--gold)',
                border: 'none', borderRadius: 'var(--r)',
                color: '#000', fontFamily: 'var(--font-space-grotesk), sans-serif',
                fontWeight: 700, fontSize: 13, cursor: 'pointer',
              }}
            >
              Back to sign in
            </button>
          </>
        )}
      </div>
    </div>
  );
}

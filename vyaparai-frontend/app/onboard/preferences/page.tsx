'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Aurora, Logo, PrefsForm, Steps, ThemeToggle } from '@/components/ui';
import { useAuth } from '@/lib/auth-context';

function PreferencesInner() {
  const router     = useRouter();
  const params     = useSearchParams();
  const { user }   = useAuth();
  const businessId = params.get('business_id') ?? '';
  const category   = params.get('category') ?? 'restaurant';

  function done() {
    router.push('/dashboard');
  }

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)',
      display: 'flex', flexDirection: 'column',
    }}>
      <Aurora />

      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'var(--nav-bg)', backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)', height: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px',
      }}>
        <Logo />
        <ThemeToggle />
      </nav>

      <main style={{ maxWidth: 720, margin: '0 auto', padding: 32, width: '100%' }}>
        <Steps active={3} />
        <h1 style={{ marginTop: 32, marginBottom: 8 }}>How should we benchmark you?</h1>
        <p style={{ color: 'var(--muted)', marginBottom: 24, fontSize: 14 }}>
          Pick your competition or let Refloat figure it out — you can change this anytime.
        </p>

        {!businessId ? (
          <p style={{ color: '#c33' }}>Missing business id — please restart onboarding.</p>
        ) : (
          <PrefsForm
            businessId={businessId}
            category={category}
            userId={user?.id}
            onSaved={done}
            onSkip={done}
          />
        )}
      </main>
    </div>
  );
}

export default function PreferencesPage() {
  return (
    <Suspense fallback={null}>
      <PreferencesInner />
    </Suspense>
  );
}

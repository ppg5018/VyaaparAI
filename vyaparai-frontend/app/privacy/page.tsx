import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy — Refloat',
  description: 'How Refloat collects, uses, and protects your data.',
};

export default function PrivacyPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', padding: '60px 20px' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>

        <Link href="/" style={{ fontSize: 13, color: 'var(--text3)', textDecoration: 'none', display: 'inline-block', marginBottom: 32 }}>
          ← Back
        </Link>

        <h1 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 700, fontSize: 32, letterSpacing: '-0.03em', margin: '0 0 8px' }}>
          Privacy Policy
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text3)', margin: '0 0 48px' }}>
          Last updated: April 2026
        </p>

        {[
          {
            title: '1. What we collect',
            body: `When you sign in with Google, we receive your name, email address, and profile photo from Google. We store this to identify your account. We also collect business details you enter during onboarding (business name, category, Google Place ID) and any POS sales data you choose to upload.`,
          },
          {
            title: '2. How we use your data',
            body: `Your data is used solely to generate your business health score and AI-powered insights. We call the Google Places API to fetch your business reviews and nearby competitors, and we call the Anthropic Claude API to generate insights. We do not sell your data to third parties.`,
          },
          {
            title: '3. Data storage',
            body: `Your data is stored in Supabase (PostgreSQL) hosted on AWS infrastructure. POS records and health scores are associated with your account and retained indefinitely unless you request deletion.`,
          },
          {
            title: '4. Third-party services',
            body: `We use Google OAuth for authentication, Google Places API for business data, Anthropic Claude API for AI insights, and Supabase for database hosting. Each of these services has its own privacy policy.`,
          },
          {
            title: '5. Cookies & sessions',
            body: `We use cookies only to maintain your login session via Supabase Auth. We do not use advertising or tracking cookies.`,
          },
          {
            title: '6. Your rights',
            body: `You can request deletion of your account and all associated data at any time by emailing us. We will process deletion requests within 30 days.`,
          },
          {
            title: '7. Contact',
            body: `For privacy-related questions or data deletion requests, email us at privacy@refloat.in.`,
          },
        ].map((section) => (
          <div key={section.title} style={{ marginBottom: 36 }}>
            <h2 style={{ fontFamily: 'var(--font-space-grotesk), sans-serif', fontWeight: 600, fontSize: 16, letterSpacing: '-0.01em', margin: '0 0 10px', color: 'var(--text)' }}>
              {section.title}
            </h2>
            <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.75, margin: 0 }}>
              {section.body}
            </p>
          </div>
        ))}

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 24, marginTop: 48 }}>
          <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>
            Refloat — AI-powered business health insights for Indian MSMEs ·{' '}
            <Link href="/terms" style={{ color: 'var(--text3)', textDecoration: 'underline' }}>Terms of Service</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

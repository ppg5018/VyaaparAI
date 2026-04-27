import type { Metadata } from 'next';
import { Space_Grotesk, DM_Sans, Space_Mono } from 'next/font/google';
import { ThemeProvider } from '@/lib/theme-context';
import { BusinessProvider } from '@/lib/business-context';
import { AuthProvider } from '@/lib/auth-context';
import './globals.css';

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-space-grotesk',
});

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-dm-sans',
});

const spaceMono = Space_Mono({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-space-mono',
});

export const metadata: Metadata = {
  title: 'Refloat — Business Health Monitor',
  description: 'AI-powered business health insights for Indian MSMEs',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark">
      <body
        className={`${spaceGrotesk.variable} ${dmSans.variable} ${spaceMono.variable}`}
        style={{
          fontFamily: "'DM Sans', sans-serif",
          background: 'var(--bg)',
          color: 'var(--text)',
        }}
      >
        <ThemeProvider>
          <AuthProvider>
            <BusinessProvider>{children}</BusinessProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

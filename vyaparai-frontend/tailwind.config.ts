import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        bg2: 'var(--bg2)',
        surface: 'var(--surface)',
        surface2: 'var(--surface2)',
        border: 'var(--border)',
        border2: 'var(--border2)',
        gold: 'var(--gold)',
        'gold-dim': 'var(--gold-dim)',
        'gold-glow': 'var(--gold-glow)',
        emerald: 'var(--emerald)',
        'emerald-dim': 'var(--emerald-dim)',
        violet: 'var(--violet)',
        'violet-dim': 'var(--violet-dim)',
        red: 'var(--red)',
        'red-dim': 'var(--red-dim)',
        yellow: 'var(--yellow)',
        'yellow-dim': 'var(--yellow-dim)',
        text: 'var(--text)',
        text2: 'var(--text2)',
        text3: 'var(--text3)',
        'nav-bg': 'var(--nav-bg)',
      },
      borderRadius: {
        r: 'var(--r)',
        r2: 'var(--r2)',
        r3: 'var(--r3)',
      },
      fontFamily: {
        grotesk: ['var(--font-space-grotesk)', 'sans-serif'],
        sans: ['var(--font-dm-sans)', 'sans-serif'],
        mono: ['var(--font-space-mono)', 'monospace'],
      },
      keyframes: {
        drift: {
          '0%':   { transform: 'translate(0,0) scale(1)' },
          '33%':  { transform: 'translate(60px,-40px) scale(1.08)' },
          '66%':  { transform: 'translate(-40px,60px) scale(0.95)' },
          '100%': { transform: 'translate(0,0) scale(1)' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0.4' },
        },
        pageIn: {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        drift:      'drift 20s ease-in-out infinite',
        pulse:      'pulse 2s ease-in-out infinite',
        'spin-slow': 'spin 1.5s linear infinite',
        'page-in':  'pageIn 0.4s ease both',
        'fade-up':  'fadeUp 0.3s ease both',
      },
    },
  },
  plugins: [],
};
export default config;

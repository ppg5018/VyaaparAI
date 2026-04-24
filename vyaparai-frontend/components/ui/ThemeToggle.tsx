'use client';

import { useTheme } from '@/lib/theme-context';

export default function ThemeToggle() {
  const { dark, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      style={{
        width: 32,
        height: 32,
        borderRadius: '50%',
        background: 'var(--surface2)',
        border: '1px solid var(--border2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'background 150ms, border-color 150ms',
        padding: 0,
      }}
    >
      {dark ? (
        /* Sun — shown in dark mode to switch to light */
        <svg
          width={16}
          height={16}
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text2)"
          strokeWidth={2}
          strokeLinecap="round"
        >
          <circle cx={12} cy={12} r={4.5} />
          <line x1={12} y1={2} x2={12} y2={4} />
          <line x1={12} y1={20} x2={12} y2={22} />
          <line x1={4.22} y1={4.22} x2={5.64} y2={5.64} />
          <line x1={18.36} y1={18.36} x2={19.78} y2={19.78} />
          <line x1={2} y1={12} x2={4} y2={12} />
          <line x1={20} y1={12} x2={22} y2={12} />
          <line x1={4.22} y1={19.78} x2={5.64} y2={18.36} />
          <line x1={18.36} y1={5.64} x2={19.78} y2={4.22} />
        </svg>
      ) : (
        /* Moon — shown in light mode to switch to dark */
        <svg
          width={16}
          height={16}
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text2)"
          strokeWidth={2}
          strokeLinecap="round"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

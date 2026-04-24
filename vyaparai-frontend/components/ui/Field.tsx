'use client';

import { useState } from 'react';

interface FieldProps {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  req?: boolean;
  options?: string[];
}

function EyeOpen() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx={12} cy={12} r={3} />
    </svg>
  );
}

function EyeOff() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1={1} y1={1} x2={23} y2={23} />
    </svg>
  );
}

function Chevron() {
  return (
    <svg width={13} height={13} viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2.5,4.5 6.5,8.5 10.5,4.5" />
    </svg>
  );
}

const SHARED_INPUT_STYLE = {
  width: '100%',
  padding: '10px 14px',
  background: 'var(--surface2)',
  borderRadius: 'var(--r)',
  color: 'var(--text)',
  fontSize: 14,
  outline: 'none',
  transition: 'border-color 0.15s ease',
  boxSizing: 'border-box' as const,
  fontFamily: 'inherit',
};

const LABEL_STYLE = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.1em',
  textTransform: 'uppercase' as const,
  color: 'var(--text2)',
};

export default function Field({
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  hint,
  req,
  options,
}: FieldProps) {
  const [focused, setFocused] = useState(false);
  const [showPw, setShowPw]   = useState(false);

  const border = `1px solid ${focused ? 'var(--gold)' : 'var(--border)'}`;

  // ── SELECT ────────────────────────────────────────
  if (type === 'select' && options) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
        <label style={LABEL_STYLE}>
          {label}
          {req && <span style={{ color: 'var(--gold)', marginLeft: 3 }}>*</span>}
        </label>

        <div style={{ position: 'relative' }}>
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            style={{
              ...SHARED_INPUT_STYLE,
              border,
              paddingRight: 36,
              appearance: 'none',
              cursor: 'pointer',
              color: value ? 'var(--text)' : 'var(--text3)',
            }}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>

          {/* Custom chevron */}
          <span
            style={{
              position: 'absolute',
              right: 11,
              top: '50%',
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
              color: 'var(--text3)',
              display: 'flex',
            }}
          >
            <Chevron />
          </span>
        </div>

        {hint && <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>{hint}</p>}
      </div>
    );
  }

  // ── TEXT / EMAIL / PASSWORD / TEL ─────────────────
  const isPassword = type === 'password';
  const inputType  = isPassword ? (showPw ? 'text' : 'password') : type;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      <label style={LABEL_STYLE}>
        {label}
        {req && <span style={{ color: 'var(--gold)', marginLeft: 3 }}>*</span>}
      </label>

      <div style={{ position: 'relative' }}>
        <input
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder}
          style={{
            ...SHARED_INPUT_STYLE,
            border,
            paddingRight: isPassword ? 42 : 14,
          }}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPw((p) => !p)}
            aria-label={showPw ? 'Hide password' : 'Show password'}
            style={{
              position: 'absolute',
              right: 10,
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              color: 'var(--text3)',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            {showPw ? <EyeOff /> : <EyeOpen />}
          </button>
        )}
      </div>

      {hint && <p style={{ fontSize: 12, color: 'var(--text3)', margin: 0 }}>{hint}</p>}
    </div>
  );
}

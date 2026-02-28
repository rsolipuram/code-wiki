/**
 * InfoBox — gradient background + primary left border matching mock .info-box.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 */

import { type ReactNode } from 'react';

interface InfoBoxProps {
  children: ReactNode;
  variant?: 'primary' | 'info' | 'warning' | 'error' | 'success';
}

const COLORS: Record<NonNullable<InfoBoxProps['variant']>, { bg: string; border: string }> = {
  primary: {
    bg: 'linear-gradient(135deg, rgba(139,92,246,0.15), rgba(6,182,212,0.15))',
    border: 'var(--primary)',
  },
  info: {
    bg: 'linear-gradient(135deg, rgba(139,92,246,0.15), rgba(6,182,212,0.15))',
    border: 'var(--primary)',
  },
  warning: {
    bg: 'linear-gradient(135deg, rgba(245,158,11,0.15), rgba(239,68,68,0.1))',
    border: 'var(--warning)',
  },
  error: {
    bg: 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(245,158,11,0.1))',
    border: 'var(--error)',
  },
  success: {
    bg: 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(6,182,212,0.1))',
    border: 'var(--success)',
  },
};

export function InfoBox({ children, variant = 'primary' }: InfoBoxProps) {
  const { bg, border } = COLORS[variant];
  return (
    <div
      style={{
        background: bg,
        borderLeft: `4px solid ${border}`,
        padding: '24px',
        borderRadius: '12px',
        margin: '32px 0',
        backdropFilter: 'blur(10px)',
      }}
    >
      {children}
    </div>
  );
}

/**
 * TypeBadge — entity type color badges matching mock type styling.
 * Types: function (secondary/cyan), class (primary/purple), method (accent/pink),
 *        module (warning/amber), interface (success/green), variable (tertiary).
 */

import { type CSSProperties } from 'react';

type EntityType = 'function' | 'class' | 'method' | 'module' | 'interface' | 'variable';

interface TypeBadgeProps {
  type: string;
  style?: CSSProperties;
}

const TYPE_STYLES: Record<EntityType, { bg: string; color: string; border: string }> = {
  function: {
    bg: 'rgba(6,182,212,0.15)',
    color: 'var(--secondary)',
    border: 'rgba(6,182,212,0.3)',
  },
  class: {
    bg: 'rgba(139,92,246,0.15)',
    color: 'var(--primary-light)',
    border: 'rgba(139,92,246,0.3)',
  },
  method: {
    bg: 'rgba(236,72,153,0.15)',
    color: 'var(--accent)',
    border: 'rgba(236,72,153,0.3)',
  },
  module: {
    bg: 'rgba(245,158,11,0.15)',
    color: '#F59E0B',
    border: 'rgba(245,158,11,0.3)',
  },
  interface: {
    bg: 'rgba(16,185,129,0.15)',
    color: 'var(--success)',
    border: 'rgba(16,185,129,0.3)',
  },
  variable: {
    bg: 'rgba(156,163,175,0.15)',
    color: 'var(--text-tertiary)',
    border: 'rgba(156,163,175,0.3)',
  },
};

const DEFAULT_STYLE = {
  bg: 'rgba(156,163,175,0.1)',
  color: 'var(--text-tertiary)',
  border: 'rgba(156,163,175,0.2)',
};

export function TypeBadge({ type, style: extraStyle }: TypeBadgeProps) {
  const s = TYPE_STYLES[type as EntityType] ?? DEFAULT_STYLE;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: '0.02em',
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        fontFamily: "'Fira Code', monospace",
        ...extraStyle,
      }}
    >
      {type}
    </span>
  );
}

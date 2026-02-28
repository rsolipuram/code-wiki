/**
 * GlassCard — frosted glass container matching .glass-card in the mock design system.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/home.html (.glass-card)
 * Properties verified:
 *   background: rgba(15,15,25,0.7) (--glass-bg)
 *   backdrop-filter: blur(20px)
 *   border: 1px solid rgba(255,255,255,0.1) (--glass-border)
 *   border-radius: 20px (--radius-lg)
 *   box-shadow: 0 8px 32px 0 rgba(0,0,0,0.37) (--shadow-glass)
 */

import { type ReactNode, type CSSProperties, type MouseEventHandler, type ElementType } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: ElementType;
  onClick?: MouseEventHandler<HTMLElement>;
  onMouseOver?: MouseEventHandler<HTMLElement>;
  onMouseOut?: MouseEventHandler<HTMLElement>;
}

export function GlassCard({
  children,
  className = '',
  style,
  as: Tag = 'div',
  onClick,
  onMouseOver,
  onMouseOut,
}: GlassCardProps) {
  return (
    <Tag
      className={`glass-card ${className}`}
      style={style}
      onClick={onClick}
      onMouseOver={onMouseOver}
      onMouseOut={onMouseOut}
    >
      {children}
    </Tag>
  );
}

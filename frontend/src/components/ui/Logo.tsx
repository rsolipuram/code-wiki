/**
 * Logo — icon + text matching the mock .logo, .logo-icon, .logo-text styles.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/home.html
 * Icon: 48×48px gradient (primary→secondary), border-radius 14px, glow shadow
 * Text: gradient (primary-light→secondary), 24px/700 weight
 */

import Link from 'next/link';

interface LogoProps {
  href?: string;
  size?: 'sm' | 'md';
}

export function Logo({ href = '/', size = 'md' }: LogoProps) {
  const iconStyle =
    size === 'sm'
      ? { width: 36, height: 36, fontSize: 16, borderRadius: 10 }
      : { width: 48, height: 48, fontSize: 20, borderRadius: 14 };

  const textStyle =
    size === 'sm' ? { fontSize: 18 } : { fontSize: 24 };

  const content = (
    <div className="logo">
      <div
        className="logo-icon"
        style={{
          ...iconStyle,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 800,
        }}
      >
        {'</>'}
      </div>
      <span className="logo-text" style={textStyle}>
        code wiki
      </span>
    </div>
  );

  return href ? <Link href={href}>{content}</Link> : content;
}

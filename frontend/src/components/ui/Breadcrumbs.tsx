/**
 * Breadcrumbs — matching mock .breadcrumbs + .breadcrumb-link styles.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 */

import Link from 'next/link';

export interface Crumb {
  label: string;
  href?: string;
}

interface BreadcrumbsProps {
  crumbs: Crumb[];
}

export function Breadcrumbs({ crumbs }: BreadcrumbsProps) {
  return (
    <nav
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 14,
        marginBottom: 32,
        color: 'var(--text-tertiary)',
      }}
    >
      {crumbs.map((crumb, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {i > 0 && <span>/</span>}
          {crumb.href ? (
            <Link
              href={crumb.href}
              style={{
                color: 'var(--text-tertiary)',
                textDecoration: 'none',
                transition: 'color 0.3s',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
              onMouseOut={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
            >
              {crumb.label}
            </Link>
          ) : (
            <span style={{ color: 'var(--text-secondary)' }}>{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

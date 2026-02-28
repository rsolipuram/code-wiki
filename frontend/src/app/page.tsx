'use client';

/**
 * Landing page — navigation hub matching index.html mock.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/index.html
 */

import Link from 'next/link';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';

const PAGE_GROUPS = [
  {
    category: 'Onboarding',
    color: 'var(--secondary)',
    pages: [
      { label: 'Submit Repository', href: '/submit', desc: 'Add a new repo for analysis' },
      { label: 'Analysis Progress', href: '/demo/progress', desc: 'Live pipeline status' },
      { label: 'Login', href: '/login', desc: 'OAuth authentication' },
    ],
  },
  {
    category: 'Wiki',
    color: 'var(--primary-light)',
    pages: [
      { label: 'Dashboard', href: '/dashboard', desc: 'All repositories' },
      { label: 'Repo Home', href: '/demo', desc: 'Wiki overview + stats' },
      { label: 'Module Page', href: '/demo/modules/api', desc: '8-section module docs' },
      { label: 'Function Detail', href: '/demo/entities/authenticate', desc: 'Entity deep-dive' },
    ],
  },
  {
    category: 'Tools',
    color: 'var(--accent)',
    pages: [
      { label: 'Search', href: '/demo/search', desc: 'Hybrid keyword + semantic' },
      { label: 'AI Chat', href: '/demo/chat', desc: 'Repo-scoped assistant' },
      { label: 'Getting Started', href: '/demo/getting-started', desc: 'Setup guide' },
      { label: 'Glossary', href: '/demo/glossary', desc: 'Domain terms' },
      { label: 'API Reference', href: '/demo/api', desc: 'Full API index' },
      { label: 'Diagrams', href: '/demo/diagrams', desc: 'Architecture views' },
    ],
  },
  {
    category: 'States',
    color: '#F59E0B',
    pages: [
      { label: 'Error / 404', href: '/not-found', desc: 'Error states' },
    ],
  },
];

export default function LandingPage() {
  return (
    <>
      <GradientBackground />
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '60px 24px' }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 64 }} className="animate-fade-in-up">
          <Logo href="/" />
          <h1
            style={{ fontSize: 48, fontWeight: 800, marginTop: 24, marginBottom: 16 }}
            className="gradient-text"
          >
            Complete UX Prototype
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 18, maxWidth: 600, margin: '0 auto' }}>
            AI-powered code documentation — all screens in one place.
          </p>
        </div>

        {/* Page groups */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 24,
          }}
          className="stagger"
        >
          {PAGE_GROUPS.map((group) => (
            <GlassCard key={group.category} className="animate-fade-in-up" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    background: group.color,
                    boxShadow: `0 0 8px ${group.color}`,
                  }}
                />
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                    color: group.color,
                  }}
                >
                  {group.category}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {group.pages.map((page) => (
                  <Link
                    key={page.href}
                    href={page.href}
                    style={{
                      display: 'block',
                      padding: '12px 16px',
                      borderRadius: 12,
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--glass-border)',
                      transition: 'all 0.2s',
                      textDecoration: 'none',
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.background = 'rgba(139,92,246,0.1)';
                      e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)';
                      e.currentTarget.style.transform = 'translateY(-2px)';
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                      e.currentTarget.style.borderColor = 'var(--glass-border)';
                      e.currentTarget.style.transform = 'none';
                    }}
                  >
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
                      {page.label}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>{page.desc}</div>
                  </Link>
                ))}
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </>
  );
}

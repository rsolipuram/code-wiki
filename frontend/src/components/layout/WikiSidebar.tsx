'use client';

/**
 * WikiSidebar — responsive sidebar with mobile hamburger/slide-in behaviour.
 *
 * Desktop (>900px): sticky sidebar, full viewport height, part of grid layout.
 * Mobile (≤900px):
 *   - Fixed topbar at top with hamburger + page title (zIndex 200, height 56px).
 *   - Sidebar is fixed off-screen (-320px) and slides in on open.
 *   - Full-screen overlay (zIndex 299), sidebar zIndex 300.
 *   - Body scroll locked when open.
 *
 * Per CLAUDE.md Mobile Nav Fix Pattern.
 */

import { useState, useCallback, useEffect } from 'react';

interface WikiSidebarProps {
  /** Nav content rendered inside the sidebar */
  children: React.ReactNode;
  /** Title shown in mobile topbar */
  pageTitle?: string;
  /** Desktop sidebar width in px; defaults to 280 */
  width?: number;
}

export function WikiSidebar({ children, pageTitle = 'Code Wiki', width = 280 }: WikiSidebarProps) {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((o) => !o), []);
  const close = useCallback(() => setOpen(false), []);

  // Body scroll lock
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [close]);

  return (
    <>
      {/* ── Fixed mobile topbar ── */}
      <div
        className="wiki-topbar"
        style={{
          display: 'none',
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 200,
          height: 56,
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderBottom: '1px solid var(--glass-border)',
          alignItems: 'center',
          padding: '0 16px',
          gap: 12,
        }}
      >
        <button
          aria-label="Open navigation"
          onClick={toggle}
          style={{
            width: 40,
            height: 40,
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--glass-border)',
            borderRadius: 10,
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 5,
            flexShrink: 0,
          }}
        >
          <span style={{ width: 18, height: 2, background: 'var(--text-primary)', borderRadius: 1 }} />
          <span style={{ width: 18, height: 2, background: 'var(--text-primary)', borderRadius: 1 }} />
          <span style={{ width: 18, height: 2, background: 'var(--text-primary)', borderRadius: 1 }} />
        </button>
        <span
          style={{
            fontSize: 15,
            fontWeight: 700,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {pageTitle}
        </span>
      </div>

      {/* ── Overlay ── */}
      {open && (
        <div
          aria-hidden="true"
          onClick={close}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 299,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(4px)',
          }}
        />
      )}

      {/* ── Sidebar ── */}
      <nav
        aria-label="Wiki navigation"
        className="wiki-sidebar"
        data-open={open ? 'true' : 'false'}
        style={{
          position: 'sticky',
          top: 0,
          height: '100vh',
          width,
          overflowY: 'auto',
          padding: '24px 0',
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderRight: '1px solid var(--glass-border)',
          flexShrink: 0,
        }}
      >
        {/* Close button (mobile) */}
        <button
          aria-label="Close navigation"
          onClick={close}
          className="wiki-sidebar-close"
          style={{
            display: 'none',
            position: 'absolute',
            top: 12,
            right: 12,
            width: 32,
            height: 32,
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--glass-border)',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: 16,
            color: 'var(--text-secondary)',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          ✕
        </button>

        {children}
      </nav>
    </>
  );
}

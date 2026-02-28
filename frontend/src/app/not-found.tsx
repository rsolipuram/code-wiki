'use client';

/**
 * 404 Not Found page — repository not found state.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/error.html (State 1)
 */

import Link from 'next/link';
import { GradientBackground } from '@/components/ui/GradientBackground';

export default function NotFound() {
  return (
    <>
      <GradientBackground />

      {/* Top Nav */}
      <nav
        style={{
          maxWidth: 900,
          margin: '0 auto',
          padding: '28px 24px 0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Link
          href="/dashboard"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--text-tertiary)',
            textDecoration: 'none',
            padding: '8px 16px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid var(--glass-border)',
            borderRadius: 10,
            backdropFilter: 'blur(8px)',
            transition: 'all 0.2s',
          }}
        >
          ← Back
        </Link>
        <Link
          href="/"
          style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: 15,
              boxShadow: '0 0 20px rgba(139,92,246,0.45)',
            }}
          >
            CW
          </div>
          <span
            style={{
              fontSize: 18,
              fontWeight: 700,
              background: 'linear-gradient(135deg, var(--primary-light), var(--secondary))',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Code Wiki
          </span>
        </Link>
      </nav>

      {/* Content */}
      <div
        style={{
          maxWidth: 780,
          margin: '0 auto',
          padding: '40px 24px 80px',
          display: 'flex',
          flexDirection: 'column',
          gap: 40,
        }}
      >
        <p
          style={{
            fontSize: 12,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: 1,
            color: 'var(--text-tertiary)',
            textAlign: 'center',
          }}
        >
          Error — Repository Not Found
        </p>

        {/* 404 Card */}
        <div
          style={{
            padding: '56px 48px',
            textAlign: 'center',
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(139,92,246,0.25)',
            borderRadius: 20,
            boxShadow: '0 8px 32px 0 rgba(0,0,0,0.37)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Top gradient bar */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              background: 'linear-gradient(90deg, var(--primary), var(--secondary))',
            }}
          />

          <div
            style={{
              fontFamily: "'Fira Code', monospace",
              fontSize: 96,
              fontWeight: 800,
              lineHeight: 1,
              marginBottom: 20,
              background: 'linear-gradient(135deg, var(--primary-light), var(--secondary))',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              letterSpacing: -4,
            }}
          >
            404
          </div>

          <h1
            style={{
              fontSize: 32,
              fontWeight: 700,
              marginBottom: 16,
              color: 'var(--text-primary)',
            }}
          >
            Repository Not Found
          </h1>

          <p
            style={{
              fontSize: 16,
              color: 'var(--text-secondary)',
              marginBottom: 36,
              maxWidth: 520,
              marginLeft: 'auto',
              marginRight: 'auto',
              lineHeight: 1.7,
            }}
          >
            We couldn't find that page. Make sure the URL is correct and the repository exists,
            or check that you have permission to access it.
          </p>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <Link
              href="/submit"
              style={{
                padding: '13px 28px',
                background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                border: 'none',
                borderRadius: 12,
                color: 'white',
                fontFamily: "'Outfit', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                textDecoration: 'none',
                boxShadow: '0 4px 20px rgba(139,92,246,0.35)',
                transition: 'all 0.3s',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              🔍 Try a different URL
            </Link>
            <Link
              href="/dashboard"
              style={{
                padding: '13px 28px',
                background: 'transparent',
                border: '1px solid var(--glass-border)',
                borderRadius: 12,
                color: 'var(--text-secondary)',
                fontFamily: "'Outfit', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'all 0.3s',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                backdropFilter: 'blur(8px)',
              }}
            >
              🏠 Go to Dashboard
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}

'use client';

/**
 * Submit page — add a new repository for analysis.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/submit.html
 */

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';
import { api } from '@/services/api';

// Provider detection regex patterns
const PROVIDER_PATTERNS = [
  {
    pattern: /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+/i,
    label: 'GitHub detected',
    cls: 'pill-github',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
      </svg>
    ),
  },
  {
    pattern: /^https?:\/\/(www\.)?gitlab\.com\/[\w.-]+\/[\w.-]+/i,
    label: 'GitLab detected',
    cls: 'pill-gitlab',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 01-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 014.82 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0118.6 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.51L23 13.45a.84.84 0 01-.35.94z" />
      </svg>
    ),
  },
  {
    pattern: /^https?:\/\/(www\.)?bitbucket\.org\/[\w.-]+\/[\w.-]+/i,
    label: 'Bitbucket detected',
    cls: 'pill-bitbucket',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M.778 1.213a.768.768 0 00-.768.892l3.263 19.81c.084.5.515.878 1.022.878h15.46c.346 0 .64-.244.7-.585L23.99 2.105a.768.768 0 00-.768-.892zm14.52 12.973h-6.62l-1.14-6.42h8.83l-1.07 6.42z" />
      </svg>
    ),
  },
];

const VALID_URL = /^https?:\/\/(github\.com|gitlab\.com|bitbucket\.org)\/[\w.-]+\/[\w.-]+(\.git)?\/?$/i;

type UrlState = 'empty' | 'valid' | 'invalid';
type Visibility = 'public' | 'private';

export default function SubmitPage() {
  const router = useRouter();
  const [url, setUrl] = useState('');
  const [urlState, setUrlState] = useState<UrlState>('empty');
  const [detectedProvider, setDetectedProvider] = useState<(typeof PROVIDER_PATTERNS)[0] | null>(null);
  const [visibility, setVisibility] = useState<Visibility>('public');
  const [branch, setBranch] = useState('main');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const handleUrlChange = useCallback((val: string) => {
    setUrl(val);
    setSubmitError('');

    if (!val.trim()) {
      setUrlState('empty');
      setDetectedProvider(null);
      return;
    }

    const provider = PROVIDER_PATTERNS.find((p) => p.pattern.test(val)) ?? null;
    setDetectedProvider(provider);
    setUrlState(VALID_URL.test(val.trim()) ? 'valid' : 'invalid');
  }, []);

  const handleSubmit = async () => {
    if (urlState !== 'valid' || submitting) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      const repo = await api.repositories.create(url.trim(), undefined, branch);
      router.push(`/${repo.owner}/${repo.name}/progress?id=${repo.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to submit repository';
      setSubmitError(msg);
      setSubmitting(false);
    }
  };

  const pillStyle: Record<string, React.CSSProperties> = {
    'pill-github': {
      background: 'rgba(230, 237, 243, 0.1)',
      border: '1px solid rgba(230, 237, 243, 0.25)',
      color: '#e6edf3',
    },
    'pill-gitlab': {
      background: 'rgba(252, 109, 38, 0.1)',
      border: '1px solid rgba(252, 109, 38, 0.3)',
      color: '#FC6D26',
    },
    'pill-bitbucket': {
      background: 'rgba(0, 82, 204, 0.1)',
      border: '1px solid rgba(0, 82, 204, 0.3)',
      color: '#5b9bd5',
    },
  };

  const inputBorderStyle: React.CSSProperties =
    urlState === 'valid'
      ? { borderColor: '#22c55e', boxShadow: '0 0 16px rgba(34,197,94,0.2)' }
      : urlState === 'invalid'
      ? { borderColor: '#ef4444', boxShadow: '0 0 16px rgba(239,68,68,0.2)' }
      : {};

  return (
    <>
      <GradientBackground />

      {/* Top bar */}
      <div
        style={{
          padding: '20px 32px',
          display: 'flex',
          alignItems: 'center',
          gap: 20,
        }}
        className="animate-fade-in-up"
      >
        <Link
          href="/dashboard"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            color: 'var(--text-tertiary)',
            fontSize: 14,
            fontWeight: 500,
            transition: 'color 0.2s',
          }}
          onMouseOver={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
          onMouseOut={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Back to repositories
        </Link>
        <Logo href="/dashboard" size="sm" />
      </div>

      {/* Two-column content */}
      <div
        style={{
          maxWidth: 1100,
          margin: '0 auto',
          padding: '0 32px 80px',
          display: 'grid',
          gridTemplateColumns: '1fr 380px',
          gap: 28,
          alignItems: 'start',
        }}
      >
        {/* ── Left: Form ── */}
        <GlassCard style={{ padding: '40px 36px' }} className="animate-fade-in-up">
          <h1
            style={{
              fontSize: 28,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              marginBottom: 24,
            }}
          >
            Add Repository
          </h1>

          {/* Stepper */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 36 }}>
            {(['Connect', 'Configure', 'Processing'] as const).map((label, i) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', flex: i < 2 ? 1 : 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 700,
                      flexShrink: 0,
                      ...(i === 0
                        ? {
                            background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                            color: 'white',
                            boxShadow: '0 0 16px rgba(139,92,246,0.5)',
                          }
                        : {
                            background: 'rgba(255,255,255,0.06)',
                            border: '1px solid var(--glass-border)',
                            color: 'var(--text-tertiary)',
                          }),
                    }}
                  >
                    {i + 1}
                  </div>
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: i === 0 ? 'var(--primary-light)' : 'var(--text-tertiary)',
                    }}
                  >
                    {label}
                  </span>
                </div>
                {i < 2 && (
                  <div
                    style={{
                      flex: 1,
                      height: 1,
                      background: 'var(--glass-border)',
                      margin: '0 12px',
                    }}
                  />
                )}
              </div>
            ))}
          </div>

          <p style={{ fontSize: 13, color: 'var(--text-tertiary)', fontWeight: 500, marginBottom: 28 }}>
            Step 1 of 2: Connect your repository
          </p>

          {/* Repository URL */}
          <div style={{ marginBottom: 22 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Repository URL
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="url"
                value={url}
                onChange={(e) => handleUrlChange(e.target.value)}
                placeholder="https://github.com/owner/repo"
                autoComplete="off"
                spellCheck={false}
                style={{
                  width: '100%',
                  padding: '14px 48px 14px 18px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 12,
                  color: 'var(--text-primary)',
                  fontFamily: "'Fira Code', monospace",
                  fontSize: 14,
                  transition: 'all 0.3s',
                  minHeight: 50,
                  outline: 'none',
                  ...inputBorderStyle,
                }}
                onFocus={(e) => {
                  if (urlState === 'empty') {
                    e.currentTarget.style.borderColor = 'var(--primary)';
                    e.currentTarget.style.boxShadow = '0 0 20px rgba(139,92,246,0.25)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.07)';
                  }
                }}
                onBlur={(e) => {
                  if (urlState === 'empty') {
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                  }
                }}
              />
              {urlState !== 'empty' && (
                <span
                  style={{
                    position: 'absolute',
                    right: 14,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    fontSize: 16,
                    color: urlState === 'valid' ? '#22c55e' : '#ef4444',
                    pointerEvents: 'none',
                  }}
                >
                  {urlState === 'valid' ? '✓' : '✕'}
                </span>
              )}
            </div>

            {urlState === 'invalid' && (
              <p style={{ fontSize: 12, color: '#f87171', marginTop: 6 }}>
                Invalid repository URL. Use https://github.com/owner/repo format.
              </p>
            )}

            {detectedProvider && (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  marginTop: 10,
                  ...pillStyle[detectedProvider.cls],
                }}
              >
                {detectedProvider.icon}
                <span>{detectedProvider.label}</span>
              </div>
            )}
          </div>

          {/* Visibility toggle */}
          <div style={{ marginBottom: 22 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Repository Visibility
            </label>
            <div
              style={{
                display: 'flex',
                borderRadius: 12,
                overflow: 'hidden',
                border: '1px solid var(--glass-border)',
                background: 'rgba(255,255,255,0.03)',
              }}
            >
              {(['public', 'private'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setVisibility(v)}
                  style={{
                    flex: 1,
                    padding: '12px 20px',
                    textAlign: 'center',
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    fontFamily: "'Outfit', sans-serif",
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    minHeight: 48,
                    ...(visibility === v
                      ? {
                          background: 'rgba(139,92,246,0.2)',
                          color: 'var(--primary-light)',
                          border: '1px solid rgba(139,92,246,0.4)',
                          borderRadius: 10,
                          margin: -1,
                        }
                      : { color: 'var(--text-tertiary)' }),
                  }}
                >
                  {v === 'public' ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                  )}
                  {v.charAt(0).toUpperCase() + v.slice(1)}
                </button>
              ))}
            </div>

            {/* OAuth subcard for private */}
            {visibility === 'private' && (
              <div
                style={{
                  padding: 20,
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 14,
                  marginTop: 14,
                }}
                className="animate-fade-in"
              >
                <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>
                  Connect GitHub Account to access private repos
                </p>
                <a
                  href="#"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '11px 20px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid var(--glass-border)',
                    borderLeft: '3px solid #e6edf3',
                    borderRadius: 10,
                    color: 'var(--text-primary)',
                    fontFamily: "'Outfit', sans-serif",
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    textDecoration: 'none',
                    minHeight: 44,
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                  </svg>
                  Connect GitHub Account
                </a>
              </div>
            )}
          </div>

          {/* Branch */}
          <div style={{ marginBottom: 22 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Branch to analyze
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              style={{
                width: '100%',
                padding: '14px 18px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: 12,
                color: 'var(--text-primary)',
                fontFamily: "'Outfit', sans-serif",
                fontSize: 14,
                outline: 'none',
                minHeight: 50,
                transition: 'all 0.3s',
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = 'var(--primary)';
                e.currentTarget.style.boxShadow = '0 0 20px rgba(139,92,246,0.25)';
                e.currentTarget.style.background = 'rgba(255,255,255,0.07)';
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = 'var(--glass-border)';
                e.currentTarget.style.boxShadow = 'none';
                e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
              }}
            />
          </div>

          {submitError && (
            <p style={{ fontSize: 13, color: '#f87171', marginBottom: 12 }}>{submitError}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={urlState !== 'valid' || submitting}
            style={{
              width: '100%',
              padding: '16px 24px',
              background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
              border: 'none',
              borderRadius: 14,
              color: 'white',
              fontFamily: "'Outfit', sans-serif",
              fontWeight: 700,
              fontSize: 16,
              cursor: urlState === 'valid' && !submitting ? 'pointer' : 'not-allowed',
              transition: 'all 0.3s',
              boxShadow: '0 4px 20px rgba(139,92,246,0.35)',
              marginTop: 8,
              minHeight: 54,
              opacity: urlState === 'valid' && !submitting ? 1 : 0.5,
            }}
            onMouseOver={(e) => {
              if (urlState === 'valid' && !submitting) {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 8px 30px rgba(139,92,246,0.55)';
              }
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'none';
              e.currentTarget.style.boxShadow = '0 4px 20px rgba(139,92,246,0.35)';
            }}
          >
            {submitting ? 'Submitting…' : 'Submit Repository →'}
          </button>
        </GlassCard>

        {/* ── Right: Info panel ── */}
        <GlassCard
          style={{
            padding: '36px 30px',
            background: 'var(--panel-strong-bg)',
            position: 'sticky',
            top: 24,
          }}
          className="animate-fade-in-up"
        >
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 24 }}>What happens next?</h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginBottom: 36 }}>
            {[
              { icon: '🔒', title: 'Secure clone', desc: 'We clone your repository in an isolated environment with read-only access.' },
              { icon: '🧠', title: 'AI code analysis', desc: 'AI analyzes code structure, modules, and relationships (~10 min for medium repos).' },
              { icon: '📄', title: 'Wiki generation', desc: 'Wiki pages are auto-generated with structured sections and cross-links.' },
              { icon: '🔁', title: 'Continuous sync', desc: 'Documentation stays in sync automatically with every commit via webhooks.' },
            ].map((step) => (
              <div key={step.title} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    background: 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(6,182,212,0.2))',
                    border: '1px solid rgba(139,92,246,0.3)',
                    borderRadius: 10,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 16,
                    flexShrink: 0,
                  }}
                >
                  {step.icon}
                </div>
                <div style={{ paddingTop: 4 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
                    {step.title}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
                    {step.desc}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ height: 1, background: 'var(--glass-border)', marginBottom: 24 }} />

          <p
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--text-tertiary)',
              textTransform: 'uppercase',
              letterSpacing: '0.8px',
              marginBottom: 14,
            }}
          >
            Supported languages
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {['Python', 'TypeScript', 'JavaScript', 'Go', 'Java', 'Rust', 'Ruby'].map((lang) => (
              <span
                key={lang}
                style={{
                  padding: '5px 12px',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 600,
                  background: 'var(--panel-soft-bg)',
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-secondary)',
                }}
              >
                {lang}
              </span>
            ))}
          </div>
        </GlassCard>
      </div>
    </>
  );
}

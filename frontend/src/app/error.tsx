'use client';

/**
 * Error boundary — analysis failure and private repo states.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/error.html (States 2 & 3)
 */

import { useState } from 'react';
import Link from 'next/link';
import { GradientBackground } from '@/components/ui/GradientBackground';

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

function isPrivateRepoError(error: Error): boolean {
  return error.message?.toLowerCase().includes('private') ||
    error.message?.toLowerCase().includes('forbidden') ||
    error.message?.toLowerCase().includes('401') ||
    error.message?.toLowerCase().includes('403');
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  const [traceOpen, setTraceOpen] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [token, setToken] = useState('');

  const isPrivate = isPrivateRepoError(error);

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
        {isPrivate ? (
          /* ===== STATE 3: Private Repository ===== */
          <>
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
              Private Repository
            </p>

            <div
              style={{
                padding: '56px 48px',
                textAlign: 'center',
                background: 'var(--glass-bg)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(6,182,212,0.25)',
                borderRadius: 20,
                boxShadow: '0 8px 32px 0 rgba(0,0,0,0.37)',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 3,
                  background: 'linear-gradient(90deg, var(--secondary), var(--primary))',
                }}
              />

              {/* Lock icon */}
              <div
                style={{
                  width: 72,
                  height: 72,
                  background: 'linear-gradient(135deg, rgba(6,182,212,0.25), rgba(6,182,212,0.1))',
                  border: '2px solid rgba(6,182,212,0.45)',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 32,
                  margin: '0 auto 24px',
                  boxShadow: '0 0 30px rgba(6,182,212,0.2)',
                }}
              >
                🔒
              </div>

              <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 16, color: 'var(--text-primary)' }}>
                Private Repository
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
                This repository is private. Connect your GitHub account to grant Code Wiki read
                access, or provide a Personal Access Token to continue.
              </p>

              {/* GitHub OAuth button */}
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 0 }}>
                <Link
                  href="/login"
                  style={{
                    padding: '14px 32px',
                    background: 'linear-gradient(135deg, #1f2937, #374151)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: 12,
                    color: 'white',
                    fontFamily: "'Outfit', sans-serif",
                    fontSize: 15,
                    fontWeight: 600,
                    textDecoration: 'none',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                    transition: 'all 0.3s',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 10,
                  }}
                >
                  <svg
                    width={20}
                    height={20}
                    viewBox="0 0 24 24"
                    fill="white"
                    aria-hidden="true"
                    style={{ flexShrink: 0 }}
                  >
                    <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                  </svg>
                  Connect GitHub Account
                </Link>
              </div>

              {/* Personal Access Token accordion */}
              <div style={{ maxWidth: 480, margin: '24px auto 0', textAlign: 'left' }}>
                <button
                  onClick={() => setTokenOpen((o) => !o)}
                  style={{
                    width: '100%',
                    padding: '12px 18px',
                    background: 'transparent',
                    border: `1px solid ${tokenOpen ? 'rgba(6,182,212,0.4)' : 'var(--glass-border)'}`,
                    borderRadius: tokenOpen ? '10px 10px 0 0' : 10,
                    color: tokenOpen ? 'var(--secondary)' : 'var(--text-tertiary)',
                    fontFamily: "'Outfit', sans-serif",
                    fontSize: 14,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.3s',
                  }}
                >
                  <span>Or enter a Personal Access Token</span>
                  <span style={{ fontSize: 10, transition: 'transform 0.3s', transform: tokenOpen ? 'rotate(180deg)' : 'none' }}>▼</span>
                </button>
                {tokenOpen && (
                  <div
                    style={{
                      padding: 20,
                      background: 'rgba(5,5,8,0.6)',
                      border: '1px solid rgba(6,182,212,0.3)',
                      borderTop: 'none',
                      borderRadius: '0 0 10px 10px',
                    }}
                  >
                    <label
                      style={{
                        fontSize: 13,
                        color: 'var(--text-tertiary)',
                        marginBottom: 8,
                        display: 'block',
                      }}
                    >
                      GitHub Personal Access Token
                    </label>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <input
                        type="password"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                        autoComplete="off"
                        spellCheck={false}
                        style={{
                          flex: 1,
                          padding: '11px 14px',
                          background: 'rgba(255,255,255,0.05)',
                          border: '1px solid var(--glass-border)',
                          borderRadius: 10,
                          color: 'var(--text-primary)',
                          fontFamily: "'Fira Code', monospace",
                          fontSize: 13,
                          outline: 'none',
                          transition: 'all 0.3s',
                        }}
                      />
                      <button
                        type="button"
                        style={{
                          padding: '11px 20px',
                          background: 'linear-gradient(135deg, var(--secondary), var(--primary))',
                          border: 'none',
                          borderRadius: 10,
                          color: 'white',
                          fontFamily: "'Outfit', sans-serif",
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                          whiteSpace: 'nowrap',
                          transition: 'all 0.3s',
                        }}
                      >
                        Connect
                      </button>
                    </div>
                    <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 10 }}>
                      Token requires <strong>repo</strong> scope.{' '}
                      <a
                        href="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--secondary)', textDecoration: 'none' }}
                      >
                        How to create a token ↗
                      </a>
                    </p>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          /* ===== STATE 2: Analysis Failed ===== */
          <>
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
              Analysis Failed
            </p>

            <div
              style={{
                padding: '56px 48px',
                textAlign: 'center',
                background: 'var(--glass-bg)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(245,158,11,0.25)',
                borderRadius: 20,
                boxShadow: '0 8px 32px 0 rgba(0,0,0,0.37)',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 3,
                  background: 'linear-gradient(90deg, #f59e0b, #ef4444)',
                }}
              />

              {/* Warning icon */}
              <div
                style={{
                  width: 72,
                  height: 72,
                  background: 'linear-gradient(135deg, rgba(245,158,11,0.25), rgba(245,158,11,0.1))',
                  border: '2px solid rgba(245,158,11,0.45)',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 32,
                  margin: '0 auto 24px',
                  boxShadow: '0 0 30px rgba(245,158,11,0.2)',
                }}
              >
                ⚠
              </div>

              <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 16, color: 'var(--text-primary)' }}>
                Analysis Failed
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
                We ran into an issue analyzing this repository. This usually happens with very large
                repos or unusual file structures. Our team has been notified.
              </p>

              {/* Expandable error details */}
              <div style={{ maxWidth: 520, margin: '0 auto 32px', textAlign: 'left' }}>
                <button
                  onClick={() => setTraceOpen((o) => !o)}
                  style={{
                    width: '100%',
                    padding: '14px 20px',
                    background: traceOpen ? 'rgba(245,158,11,0.08)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${traceOpen ? 'rgba(245,158,11,0.4)' : 'var(--glass-border)'}`,
                    borderRadius: traceOpen ? '12px 12px 0 0' : 12,
                    color: traceOpen ? '#fbbf24' : 'var(--text-secondary)',
                    fontFamily: "'Outfit', sans-serif",
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.3s',
                  }}
                >
                  <span>🗑 Error Details</span>
                  <span style={{ fontSize: 10, transition: 'transform 0.3s', transform: traceOpen ? 'rotate(180deg)' : 'none' }}>▼</span>
                </button>
                {traceOpen && (
                  <div
                    style={{
                      padding: 20,
                      background: 'rgba(5,5,8,0.7)',
                      border: '1px solid rgba(245,158,11,0.3)',
                      borderTop: 'none',
                      borderRadius: '0 0 12px 12px',
                    }}
                  >
                    <pre
                      style={{
                        fontFamily: "'Fira Code', monospace",
                        fontSize: 12,
                        lineHeight: 1.8,
                        color: '#9CA3AF',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        margin: 0,
                        textAlign: 'left',
                      }}
                    >
                      <span style={{ color: '#f87171' }}>{error.message || 'An unexpected error occurred'}</span>
                      {'\n'}
                      {error.stack && (
                        <span style={{ color: '#9CA3AF' }}>{error.stack}</span>
                      )}
                      {error.digest && (
                        <span style={{ color: 'var(--primary-light)' }}>{`\ndigest: ${error.digest}`}</span>
                      )}
                    </pre>
                  </div>
                )}
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <button
                  onClick={reset}
                  style={{
                    padding: '13px 28px',
                    background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                    border: 'none',
                    borderRadius: 12,
                    color: 'white',
                    fontFamily: "'Outfit', sans-serif",
                    fontSize: 15,
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 4px 20px rgba(139,92,246,0.35)',
                    transition: 'all 0.3s',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  ↺ Retry Analysis
                </button>
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
                  🕐 Contact Support
                </Link>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

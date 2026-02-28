'use client';

/**
 * Login page — OAuth + email/password sign-in form (UI stubs only; MVP has no auth backend).
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/login.html
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';

const OAUTH_PROVIDERS = [
  {
    id: 'github',
    label: 'Continue with GitHub',
    accentColor: '#e6edf3',
    hoverBorder: 'rgba(230,237,243,0.4)',
    hoverShadow: 'rgba(230,237,243,0.12)',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
      </svg>
    ),
  },
  {
    id: 'gitlab',
    label: 'Continue with GitLab',
    accentColor: '#FC6D26',
    hoverBorder: 'rgba(252,109,38,0.4)',
    hoverShadow: 'rgba(252,109,38,0.15)',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="#FC6D26" aria-hidden="true">
        <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 01-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 014.82 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.49h8.1l2.44-7.49a.42.42 0 01.11-.18.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.51 1.22 3.78a.84.84 0 01-.3.94z" />
      </svg>
    ),
  },
  {
    id: 'bitbucket',
    label: 'Continue with Bitbucket',
    accentColor: '#0052CC',
    hoverBorder: 'rgba(0,82,204,0.5)',
    hoverShadow: 'rgba(0,82,204,0.2)',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="#0052CC" aria-hidden="true">
        <path d="M.778 1.213a.768.768 0 00-.768.892l3.263 19.81c.084.5.515.868 1.022.873H19.95a.772.772 0 00.77-.646l3.27-20.03a.768.768 0 00-.768-.891L.778 1.213zM14.52 15.53H9.522L8.17 8.466h7.561l-1.211 7.064z" />
      </svg>
    ),
  },
] as const;

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [hoveredProvider, setHoveredProvider] = useState<string | null>(null);

  const handleEmailSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    // MVP stub: redirect to dashboard
    router.push('/dashboard');
  };

  return (
    <>
      <GradientBackground />
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
        }}
      >
        <div
          style={{
            width: '100%',
            maxWidth: 480,
            animation: 'fadeInUp 0.6s ease forwards',
          }}
        >
          {/* Logo area */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div
              style={{
                width: 64,
                height: 64,
                background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                borderRadius: 18,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 800,
                fontSize: 24,
                boxShadow: '0 0 40px rgba(139,92,246,0.5)',
                marginBottom: 16,
                color: '#fff',
              }}
            >
              CW
            </div>
            <div
              style={{
                fontSize: 28,
                fontWeight: 700,
                background: 'linear-gradient(135deg, var(--primary-light), var(--secondary))',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                display: 'block',
                marginBottom: 6,
              }}
            >
              Code Wiki
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)', letterSpacing: '0.5px' }}>
              Documentation that writes itself
            </div>
          </div>

          {/* Glass card */}
          <div
            className="glass-card"
            style={{ padding: '40px 36px' }}
          >
            <h1
              style={{
                fontSize: 26,
                fontWeight: 700,
                color: 'var(--text-primary)',
                marginBottom: 8,
                textAlign: 'center',
              }}
            >
              Sign in to Code Wiki
            </h1>
            <p
              style={{
                fontSize: 14,
                color: 'var(--text-secondary)',
                textAlign: 'center',
                marginBottom: 32,
              }}
            >
              Connect your account to start generating documentation
            </p>

            {/* OAuth buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
              {OAUTH_PROVIDERS.map((provider) => {
                const isHovered = hoveredProvider === provider.id;
                return (
                  <button
                    key={provider.id}
                    onClick={() => router.push('/dashboard')}
                    onMouseEnter={() => setHoveredProvider(provider.id)}
                    onMouseLeave={() => setHoveredProvider(null)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 14,
                      width: '100%',
                      padding: '14px 20px',
                      background: isHovered ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)',
                      border: `1px solid ${isHovered ? provider.hoverBorder : 'var(--glass-border)'}`,
                      borderRadius: 14,
                      color: 'var(--text-primary)',
                      fontFamily: 'inherit',
                      fontSize: 15,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.3s cubic-bezier(0.4,0,0.2,1)',
                      minHeight: 52,
                      transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
                      boxShadow: isHovered ? `0 6px 24px ${provider.hoverShadow}` : 'none',
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                  >
                    {/* Left accent stripe */}
                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        bottom: 0,
                        width: 4,
                        background: provider.accentColor,
                        borderRadius: '14px 0 0 14px',
                      }}
                    />
                    <span style={{ flexShrink: 0 }}>{provider.icon}</span>
                    <span style={{ flex: 1 }}>{provider.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Divider */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                marginBottom: 24,
              }}
            >
              <div style={{ flex: 1, height: 1, background: 'var(--glass-border)' }} />
              <span style={{ fontSize: 13, color: 'var(--text-tertiary)', fontWeight: 500 }}>
                or sign in with email
              </span>
              <div style={{ flex: 1, height: 1, background: 'var(--glass-border)' }} />
            </div>

            {/* Email / password form */}
            <form onSubmit={handleEmailSignIn}>
              <div style={{ marginBottom: 16 }}>
                <label
                  htmlFor="email"
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    marginBottom: 8,
                    letterSpacing: '0.3px',
                  }}
                >
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  style={{
                    width: '100%',
                    padding: '13px 16px',
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 12,
                    color: 'var(--text-primary)',
                    fontFamily: 'inherit',
                    fontSize: 15,
                    minHeight: 48,
                    outline: 'none',
                    transition: 'all 0.3s',
                  }}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = 'var(--primary)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.08)';
                    e.currentTarget.style.boxShadow = '0 0 20px rgba(139,92,246,0.25)';
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label
                  htmlFor="password"
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    marginBottom: 8,
                    letterSpacing: '0.3px',
                  }}
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{
                    width: '100%',
                    padding: '13px 16px',
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 12,
                    color: 'var(--text-primary)',
                    fontFamily: 'inherit',
                    fontSize: 15,
                    minHeight: 48,
                    outline: 'none',
                    transition: 'all 0.3s',
                  }}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = 'var(--primary)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.08)';
                    e.currentTarget.style.boxShadow = '0 0 20px rgba(139,92,246,0.25)';
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                />
              </div>

              <button
                type="submit"
                style={{
                  width: '100%',
                  padding: '15px 24px',
                  background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                  border: 'none',
                  borderRadius: 14,
                  color: '#fff',
                  fontFamily: 'inherit',
                  fontWeight: 700,
                  fontSize: 16,
                  cursor: 'pointer',
                  transition: 'all 0.3s',
                  boxShadow: '0 4px 20px rgba(139,92,246,0.35)',
                  marginTop: 8,
                  minHeight: 52,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 8px 30px rgba(139,92,246,0.55)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(139,92,246,0.35)';
                }}
                onMouseDown={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                Sign in
              </button>
            </form>

            {/* Helper links */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: 16,
              }}
            >
              <a
                href="#"
                style={{
                  fontSize: 13,
                  color: 'var(--primary-light)',
                  textDecoration: 'none',
                  transition: 'color 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--secondary)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
              >
                Don&apos;t have an account? Sign up
              </a>
              <a
                href="#"
                style={{
                  fontSize: 13,
                  color: 'var(--primary-light)',
                  textDecoration: 'none',
                  transition: 'color 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--secondary)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
              >
                Forgot password?
              </a>
            </div>

            {/* Footer */}
            <div
              style={{
                textAlign: 'center',
                marginTop: 24,
                paddingTop: 24,
                borderTop: '1px solid var(--glass-border)',
              }}
            >
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                <a
                  href="#"
                  style={{ color: 'var(--text-tertiary)', textDecoration: 'none', transition: 'color 0.2s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
                >
                  Privacy Policy
                </a>
                <span style={{ margin: '0 8px', opacity: 0.5 }}>·</span>
                <a
                  href="#"
                  style={{ color: 'var(--text-tertiary)', textDecoration: 'none', transition: 'color 0.2s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--primary-light)')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
                >
                  Terms of Service
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(30px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        input::placeholder {
          color: var(--text-tertiary);
        }
        @media (max-width: 520px) {
          .login-card-responsive {
            padding: 28px 20px !important;
          }
        }
      `}</style>
    </>
  );
}

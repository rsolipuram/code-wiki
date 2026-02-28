'use client';

/**
 * Progress page — animated analysis pipeline for a repository.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/progress.html
 */

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';
import { api } from '@/services/api';
import type { Repository } from '@/services/api';

const PIPELINE_STEPS = [
  { label: 'Cloning repository', doneDesc: 'Done' },
  { label: 'Parsing source files', doneDesc: 'Files analyzed' },
  { label: 'Detecting modules', activeDesc: 'Modules found…' },
  { label: 'Building knowledge graph', pendingDesc: 'Pending' },
  { label: 'Generating wiki pages', pendingDesc: 'Pending' },
  { label: 'Creating visual diagrams', pendingDesc: 'Pending' },
];

// Progress percentage per step (cumulative)
const STEP_PROGRESS = [10, 25, 45, 65, 85, 100];

type StepState = 'complete' | 'active' | 'pending';

function getStepStates(activeIndex: number): StepState[] {
  return PIPELINE_STEPS.map((_, i) => {
    if (i < activeIndex) return 'complete';
    if (i === activeIndex) return 'active';
    return 'pending';
  });
}

export default function ProgressPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const owner = params.owner as string;
  const name = params.name as string;
  const repoId = searchParams.get('id') ?? '';

  const [repo, setRepo] = useState<Repository | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [accordionOpen, setAccordionOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [repoStatus, setRepoStatus] = useState<Repository['status'] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll repo status every 5s
  useEffect(() => {
    if (!repoId) return;

    const poll = async () => {
      try {
        const r = await api.repositories.get(repoId);
        setRepo(r);
        setRepoStatus(r.status);
        if (r.status === 'ready') {
          clearInterval(pollRef.current!);
          clearInterval(tickRef.current!);
          setActiveStep(PIPELINE_STEPS.length); // all complete
          setDone(true);
        } else if (r.status === 'error') {
          clearInterval(pollRef.current!);
          clearInterval(tickRef.current!);
          setErrorMessage(r.error_message || 'An unexpected error occurred during analysis.');
        } else if (r.status === 'pending') {
          setActiveStep(0);
        } else if (r.status === 'analyzing') {
          // Ensure we're at least on step 1 when analyzing starts
          setActiveStep((s) => Math.max(s, 1));
        }
      } catch {
        // ignore polling errors
      }
    };

    poll();
    pollRef.current = setInterval(poll, 5000);
    return () => {
      clearInterval(pollRef.current!);
      clearInterval(tickRef.current!);
    };
  }, [repoId]);

  // Simulate step progression while analyzing (advances steps 1→4 every ~20s)
  useEffect(() => {
    if (!repoId || repoStatus !== 'analyzing') return;
    clearInterval(tickRef.current!);
    tickRef.current = setInterval(() => {
      setActiveStep((s) => {
        // Don't advance past step 4 (leave "Creating visual diagrams" for ready state)
        if (s >= 4) return s;
        return s + 1;
      });
    }, 20000);
    return () => clearInterval(tickRef.current!);
  }, [repoId, repoStatus]);

  // Simulate step progression every 8s when no repoId (demo mode)
  useEffect(() => {
    if (repoId) return;
    const timer = setInterval(() => {
      setActiveStep((s) => {
        if (s >= PIPELINE_STEPS.length - 1) {
          clearInterval(timer);
          setDone(true);
          return PIPELINE_STEPS.length;
        }
        return s + 1;
      });
    }, 8000);
    return () => clearInterval(timer);
  }, [repoId]);

  const stepStates = getStepStates(Math.min(activeStep, PIPELINE_STEPS.length - 1));
  const pct = done ? 100 : STEP_PROGRESS[Math.min(activeStep, STEP_PROGRESS.length - 1)] ?? 10;
  const displayName = repo?.name ?? name;
  const displayUrl = repo?.url ?? `github.com/${owner}/${name}`;

  const MOCK_MODULES = [
    { icon: '📦', name: 'authentication', count: '24 functions' },
    { icon: '📦', name: 'api/routes', count: '18 functions' },
    { icon: '📦', name: 'database', count: '12 functions' },
    { icon: '📦', name: 'utils', count: '31 functions' },
    { icon: '📦', name: 'middleware', count: '9 functions' },
  ];

  if (repoStatus === 'error') {
    return (
      <>
        <GradientBackground />
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '40px 24px 80px',
          }}
        >
          {/* Top bar */}
          <div
            style={{
              width: '100%',
              maxWidth: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              marginBottom: 40,
            }}
            className="animate-fade-in-up"
          >
            <Link
              href="/dashboard"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                color: 'var(--text-tertiary)',
                fontSize: 13,
                fontWeight: 500,
                textDecoration: 'none',
                minHeight: 44,
                transition: 'color 0.2s',
              }}
            >
              ← Back
            </Link>
            <div style={{ marginLeft: 'auto' }}>
              <Logo href="/dashboard" size="sm" />
            </div>
          </div>

          {/* Error card */}
          <GlassCard
            style={{
              width: '100%',
              maxWidth: 700,
              padding: '48px 44px',
              textAlign: 'center',
            }}
            className="animate-fade-in-up"
          >
            {/* Error icon */}
            <div
              style={{
                width: 80,
                height: 80,
                margin: '0 auto 24px',
                borderRadius: '50%',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '2px solid rgba(239, 68, 68, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 36,
              }}
            >
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
            </div>

            <h1
              style={{
                fontSize: 28,
                fontWeight: 800,
                color: '#f87171',
                marginBottom: 12,
              }}
            >
              Analysis Failed
            </h1>

            <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Something went wrong while analyzing {displayName}.
            </p>

            {/* Error message */}
            {errorMessage && (
              <div
                style={{
                  padding: '16px 20px',
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  borderRadius: 12,
                  marginBottom: 32,
                  textAlign: 'left',
                }}
              >
                <p
                  style={{
                    fontSize: 13,
                    fontFamily: "'Fira Code', monospace",
                    color: '#fca5a5',
                    lineHeight: 1.6,
                    wordBreak: 'break-word',
                  }}
                >
                  {errorMessage}
                </p>
              </div>
            )}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Link
                href="/submit"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '14px 28px',
                  background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                  borderRadius: 14,
                  color: 'white',
                  fontFamily: "'Outfit', sans-serif",
                  fontWeight: 700,
                  fontSize: 15,
                  textDecoration: 'none',
                  boxShadow: '0 4px 20px rgba(139,92,246,0.4)',
                  transition: 'all 0.3s',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 8px 30px rgba(139,92,246,0.6)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'none';
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(139,92,246,0.4)';
                }}
              >
                Try Again
              </Link>
              <Link
                href="/dashboard"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '14px 28px',
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 14,
                  color: 'var(--text-secondary)',
                  fontFamily: "'Outfit', sans-serif",
                  fontWeight: 600,
                  fontSize: 15,
                  textDecoration: 'none',
                  transition: 'all 0.3s',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.borderColor = 'var(--primary)';
                  e.currentTarget.style.color = 'var(--primary-light)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.borderColor = 'var(--glass-border)';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                Back to Dashboard
              </Link>
            </div>
          </GlassCard>
        </div>
      </>
    );
  }

  if (done) {
    return (
      <>
        <GradientBackground />
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '40px 24px 80px',
          }}
        >
          {/* Top bar */}
          <div
            style={{
              width: '100%',
              maxWidth: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              marginBottom: 40,
            }}
            className="animate-fade-in-up"
          >
            <Link
              href="/dashboard"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                color: 'var(--text-tertiary)',
                fontSize: 13,
                fontWeight: 500,
                textDecoration: 'none',
                minHeight: 44,
                transition: 'color 0.2s',
              }}
            >
              ← Back
            </Link>
            <div style={{ marginLeft: 'auto' }}>
              <Logo href="/dashboard" size="sm" />
            </div>
          </div>

          {/* Completion card */}
          <GlassCard
            style={{
              width: '100%',
              maxWidth: 700,
              padding: '48px 44px',
              textAlign: 'center',
            }}
            className="animate-fade-in-up"
          >
            {/* Sparkles */}
            <div
              style={{
                width: 100,
                height: 100,
                margin: '0 auto 24px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--secondary), var(--accent))',
                backgroundSize: '200% 200%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 44,
                boxShadow: '0 0 60px rgba(139,92,246,0.6)',
              }}
            >
              ✨
            </div>
            <h1
              style={{
                fontSize: 32,
                fontWeight: 800,
                background: 'linear-gradient(135deg, var(--primary-light), var(--secondary), var(--accent))',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                marginBottom: 12,
              }}
            >
              Wiki is ready!
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', marginBottom: 36 }}>
              Your documentation has been generated successfully.
            </p>
            <Link
              href={`/${owner}/${name}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                padding: '16px 36px',
                background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                borderRadius: 16,
                color: 'white',
                fontFamily: "'Outfit', sans-serif",
                fontWeight: 700,
                fontSize: 17,
                textDecoration: 'none',
                boxShadow: '0 4px 24px rgba(139,92,246,0.5)',
                transition: 'all 0.3s',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.transform = 'translateY(-3px)';
                e.currentTarget.style.boxShadow = '0 10px 36px rgba(139,92,246,0.7)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = 'none';
                e.currentTarget.style.boxShadow = '0 4px 24px rgba(139,92,246,0.5)';
              }}
            >
              View Wiki →
            </Link>
          </GlassCard>
        </div>
      </>
    );
  }

  return (
    <>
      <GradientBackground />
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '40px 24px 80px',
        }}
      >
        {/* Top bar */}
        <div
          style={{
            width: '100%',
            maxWidth: 700,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            marginBottom: 40,
          }}
          className="animate-fade-in-up"
        >
          <Link
            href="/submit"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              color: 'var(--text-tertiary)',
              fontSize: 13,
              fontWeight: 500,
              textDecoration: 'none',
              minHeight: 44,
              transition: 'color 0.2s',
            }}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back
          </Link>
          <div style={{ marginLeft: 'auto' }}>
            <Logo href="/dashboard" size="sm" />
          </div>
        </div>

        {/* Main card */}
        <GlassCard
          style={{ width: '100%', maxWidth: 700, padding: '48px 44px' }}
          className="animate-fade-in-up"
        >
          {/* Heading */}
          <h1
            style={{
              fontFamily: "'Fira Code', monospace",
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: '-0.02em',
              marginBottom: 12,
            }}
          >
            Analyzing {displayName}
          </h1>

          {/* Repo pill */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '5px 14px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--glass-border)',
              borderRadius: 20,
              fontFamily: "'Fira Code', monospace",
              fontSize: 13,
              color: 'var(--text-tertiary)',
              marginBottom: 40,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--secondary)',
                flexShrink: 0,
                display: 'inline-block',
              }}
            />
            {displayUrl}
          </div>

          {/* Vertical stepper */}
          <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 40, position: 'relative' }}>
            {PIPELINE_STEPS.map((step, i) => {
              const state = stepStates[i];
              return (
                <div
                  key={step.label}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 16,
                    paddingBottom: i < PIPELINE_STEPS.length - 1 ? 28 : 0,
                    position: 'relative',
                  }}
                >
                  {/* Connector line */}
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div
                      style={{
                        position: 'absolute',
                        left: 14,
                        top: 30,
                        bottom: 0,
                        width: 2,
                        background:
                          state === 'complete'
                            ? 'rgba(34,197,94,0.4)'
                            : state === 'active'
                            ? 'rgba(6,182,212,0.3)'
                            : 'var(--glass-border)',
                      }}
                    />
                  )}

                  {/* Step node */}
                  <div
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      fontSize: 13,
                      fontWeight: 700,
                      position: 'relative',
                      zIndex: 1,
                      transition: 'all 0.4s',
                      ...(state === 'complete'
                        ? {
                            background: '#22c55e',
                            color: 'white',
                            boxShadow: '0 0 16px rgba(34,197,94,0.5)',
                          }
                        : state === 'active'
                        ? {
                            background: 'var(--secondary)',
                            color: 'white',
                            animation: 'pulseGlow 2s infinite',
                          }
                        : {
                            background: 'rgba(255,255,255,0.05)',
                            border: '2px solid var(--glass-border)',
                            color: 'var(--text-tertiary)',
                          }),
                    }}
                  >
                    {state === 'complete' ? '✓' : i + 1}
                  </div>

                  {/* Step content */}
                  <div style={{ paddingTop: 4, flex: 1 }}>
                    <div
                      style={{
                        fontSize: 15,
                        fontWeight: 600,
                        marginBottom: 3,
                        color:
                          state === 'complete'
                            ? '#4ade80'
                            : state === 'active'
                            ? 'var(--secondary)'
                            : 'var(--text-tertiary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      {step.label}
                      {state === 'active' && (
                        <span
                          style={{
                            display: 'inline-block',
                            width: 12,
                            height: 12,
                            border: '2px solid rgba(6,182,212,0.3)',
                            borderTopColor: 'var(--secondary)',
                            borderRadius: '50%',
                            animation: 'spin 0.8s linear infinite',
                          }}
                        />
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 13,
                        color:
                          state === 'active' ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                      }}
                    >
                      {state === 'complete'
                        ? step.doneDesc ?? 'Done'
                        : state === 'active'
                        ? step.activeDesc ?? 'In progress…'
                        : step.pendingDesc ?? 'Pending'}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* CSS for step animations */}
          <style>{`
            @keyframes pulseGlow {
              0%, 100% { box-shadow: 0 0 0 0 rgba(6,182,212,0.5); }
              50%       { box-shadow: 0 0 0 8px rgba(6,182,212,0); }
            }
          `}</style>

          {/* Progress bar */}
          <div style={{ marginBottom: 28 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 10,
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--secondary)' }}>
                {pct}%
              </span>
              <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
                Estimated time remaining: ~{Math.max(1, Math.round((100 - pct) / 10))} minutes
              </span>
            </div>
            <div
              style={{
                height: 10,
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid var(--glass-border)',
                borderRadius: 100,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  borderRadius: 100,
                  background: 'linear-gradient(90deg, var(--primary), var(--secondary))',
                  boxShadow: '0 0 12px rgba(6,182,212,0.5)',
                  width: `${pct}%`,
                  transition: 'width 0.8s cubic-bezier(0.4,0,0.2,1)',
                }}
              />
            </div>
          </div>

          {/* Live stats */}
          <div
            style={{
              display: 'flex',
              gap: 20,
              flexWrap: 'wrap',
              padding: '16px 0',
              borderTop: '1px solid var(--glass-border)',
              borderBottom: '1px solid var(--glass-border)',
              marginBottom: 28,
              fontSize: 13,
            }}
          >
            {[
              { label: 'Files', val: repo?.size_files ?? '312' },
              { label: 'Modules', val: '8' },
              { label: 'Functions', val: '124' },
            ].map((s) => (
              <div
                key={s.label}
                style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-tertiary)' }}
              >
                {s.label}:{' '}
                <span style={{ color: 'var(--primary-light)', fontWeight: 700 }}>{s.val}</span>
              </div>
            ))}
          </div>

          {/* Accordion — discovered modules */}
          <div
            style={{
              borderRadius: 14,
              overflow: 'hidden',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)',
              marginBottom: 32,
            }}
          >
            <button
              onClick={() => setAccordionOpen((o) => !o)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 20px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                fontFamily: "'Outfit', sans-serif",
                minHeight: 50,
                transition: 'background 0.2s',
              }}
            >
              <span>🔍 Modules discovered so far</span>
              <span
                style={{
                  fontSize: 11,
                  color: 'var(--text-tertiary)',
                  transform: accordionOpen ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.25s',
                }}
              >
                ▼
              </span>
            </button>

            {accordionOpen && (
              <div style={{ padding: '0 20px 16px' }} className="animate-fade-in">
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {MOCK_MODULES.map((mod) => (
                    <li
                      key={mod.name}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        fontSize: 13,
                        color: 'var(--text-secondary)',
                        padding: '8px 12px',
                        background: 'rgba(255,255,255,0.03)',
                        borderRadius: 8,
                        border: '1px solid var(--glass-border)',
                      }}
                    >
                      <span style={{ fontSize: 15 }}>{mod.icon}</span>
                      <span
                        style={{
                          fontFamily: "'Fira Code', monospace",
                          color: 'var(--primary-light)',
                          fontWeight: 500,
                        }}
                      >
                        {mod.name}
                      </span>
                      <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-tertiary)' }}>
                        {mod.count}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Cancel */}
          <Link
            href="/dashboard"
            style={{
              display: 'block',
              textAlign: 'center',
              color: 'var(--text-tertiary)',
              fontSize: 14,
              textDecoration: 'none',
              transition: 'color 0.2s',
            }}
            onMouseOver={(e) => (e.currentTarget.style.color = 'var(--accent)')}
            onMouseOut={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
          >
            Cancel analysis
          </Link>
        </GlassCard>
      </div>
    </>
  );
}

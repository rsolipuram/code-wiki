'use client';

/**
 * Progress page — live pipeline telemetry for repository analysis.
 * Shows 9 real steps driven by backend progress, with live stats and elapsed time.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/progress.html
 */

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';
import { api, progressStreamUrl } from '@/services/api';
import type { Repository, PipelineProgress, AgentProgressEvent } from '@/services/api';

const PIPELINE_STEPS = [
  { label: 'Cloning repository', icon: '\u{1F4E5}' },
  { label: 'Scanning file structure', icon: '\u{1F50D}' },
  { label: 'Parsing source files', icon: '\u2699\uFE0F' },
  { label: 'Persisting entities', icon: '\u{1F4BE}' },
  { label: 'Running AI analysis', icon: '\u{1F9E0}' },
  { label: 'Building relationship graph', icon: '\u{1F517}' },
  { label: 'Detecting modules', icon: '\u{1F4E6}' },
  { label: 'Generating wiki pages', icon: '\u{1F4C4}' },
  { label: 'Finalizing', icon: '\u2728' },
];

type StepState = 'complete' | 'active' | 'pending';

function getStepStates(activeIndex: number): StepState[] {
  return PIPELINE_STEPS.map((_, i) => {
    if (i < activeIndex) return 'complete';
    if (i === activeIndex) return 'active';
    return 'pending';
  });
}

function formatElapsed(seconds?: number): string {
  if (seconds == null) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return `${m}m ${s}s elapsed`;
  return `${s}s elapsed`;
}

function formatNumber(n?: number): string {
  if (n == null) return '';
  return n.toLocaleString();
}

interface StatItem {
  label: string;
  value: string;
}

const WIKI_AGENTS = [
  { id: 'architect', label: 'Architect', desc: 'Analyzing codebase structure' },
  { id: 'planner', label: 'Planner', desc: 'Planning wiki sections' },
  { id: 'writer', label: 'Writer', desc: 'Writing technical prose' },
  { id: 'annotator', label: 'Annotator', desc: 'Adding entity references' },
  { id: 'diagrammer', label: 'Diagrammer', desc: 'Generating diagrams' },
  { id: 'tabulator', label: 'Tabulator', desc: 'Building summary tables' },
  { id: 'assembler', label: 'Assembler', desc: 'Assembling final pages' },
];

type AgentState = { status: 'pending' | 'running' | 'complete'; detail: string };

function getAgentStates(events: AgentProgressEvent[]): Record<string, AgentState> {
  const states: Record<string, AgentState> = {};
  // Pre-initialize all agents to pending
  for (const agent of WIKI_AGENTS) {
    states[agent.id] = { status: 'pending', detail: '' };
  }
  // Apply events in order (latest event for an agent wins)
  for (const e of events) {
    states[e.agent] = { status: e.status, detail: e.detail };
  }
  return states;
}

function buildLiveStats(stats?: PipelineProgress['stats']): StatItem[] {
  if (!stats) return [];
  const items: StatItem[] = [];
  if (stats.files_scanned != null) items.push({ label: 'Files', value: formatNumber(stats.files_scanned) });
  if (stats.loc != null) items.push({ label: 'Lines', value: formatNumber(stats.loc) });
  if (stats.entities_found != null) items.push({ label: 'Entities', value: formatNumber(stats.entities_found) });
  if (stats.modules_detected != null) items.push({ label: 'Modules', value: formatNumber(stats.modules_detected) });
  if (stats.agents_completed != null && stats.agents_total != null) {
    items.push({ label: 'Agents', value: `${stats.agents_completed}/${stats.agents_total}` });
  }
  if (stats.pages_generated != null && stats.pages_total != null && stats.pages_total > 0) {
    items.push({ label: 'Pages', value: `${stats.pages_generated}/${stats.pages_total}` });
  }
  return items;
}

export default function ProgressPage() {
  const params = useParams();
  const searchParams = useSearchParams();

  const owner = params.owner as string;
  const name = params.name as string;
  const repoId = searchParams.get('id') ?? '';

  const [repo, setRepo] = useState<Repository | null>(null);
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const [done, setDone] = useState(false);
  const [repoStatus, setRepoStatus] = useState<Repository['status'] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [agentEvents, setAgentEvents] = useState<AgentProgressEvent[]>([]);

  // Smooth elapsed timer — ticks locally between SSE events
  const [localElapsed, setLocalElapsed] = useState<number | null>(null);
  const lastPollElapsed = useRef<number | null>(null);
  const lastPollTime = useRef<number>(Date.now());

  // Demo mode step advancement (when no repoId)
  const [demoStep, setDemoStep] = useState(0);
  const demoRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // SSE-based progress streaming (replaces polling)
  useEffect(() => {
    if (!repoId) return;

    // Initial fetch for catch-up state
    api.repositories.get(repoId).then((r) => {
      setRepo(r);
      setRepoStatus(r.status);
      setProgress(r.progress ?? null);
      if (r.status === 'ready') { setDone(true); return; }
      if (r.status === 'error') {
        setErrorMessage(r.error_message || 'An unexpected error occurred during analysis.');
        return;
      }
    }).catch(() => {});

    // Connect to SSE stream
    const es = new EventSource(progressStreamUrl(repoId));

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'done') {
          setRepoStatus(data.status);
          if (data.status === 'ready') setDone(true);
          if (data.status === 'error') setErrorMessage(data.error || 'Analysis failed');
          es.close();
          return;
        }

        if (data.type === 'step_progress') {
          setProgress(data);
          // Receiving step events means analysis is active
          setRepoStatus((prev) => prev === 'pending' ? 'analyzing' : prev);
        }

        if (data.type === 'agent_progress') {
          setAgentEvents((prev) => [...prev, data]);
        }

        // Handle initial catch-up data (no type field = DB progress snapshot)
        if (!data.type && data.current_step) {
          setProgress(data);
          setRepoStatus((prev) => prev === 'pending' ? 'analyzing' : prev);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
      // Fallback: poll once to get final state
      api.repositories.get(repoId).then((r) => {
        setRepo(r);
        setRepoStatus(r.status);
        setProgress(r.progress ?? null);
        if (r.status === 'ready') setDone(true);
        if (r.status === 'error') setErrorMessage(r.error_message || 'Analysis failed');
      }).catch(() => {});
    };

    return () => es.close();
  }, [repoId]);

  // Demo mode: advance steps every 3s when no repoId
  useEffect(() => {
    if (repoId) return;
    demoRef.current = setInterval(() => {
      setDemoStep((s) => {
        if (s >= PIPELINE_STEPS.length - 1) {
          clearInterval(demoRef.current!);
          setDone(true);
          return PIPELINE_STEPS.length;
        }
        return s + 1;
      });
    }, 3000);
    return () => clearInterval(demoRef.current!);
  }, [repoId]);

  // Sync elapsed from poll
  useEffect(() => {
    if (progress?.elapsed_seconds != null) {
      lastPollElapsed.current = progress.elapsed_seconds;
      lastPollTime.current = Date.now();
      setLocalElapsed(progress.elapsed_seconds);
    }
  }, [progress?.elapsed_seconds]);

  // Tick elapsed every second between polls for smooth display
  const hasElapsed = localElapsed != null;
  useEffect(() => {
    if (done || repoStatus === 'error' || !hasElapsed) return;
    const timer = setInterval(() => {
      if (lastPollElapsed.current != null) {
        const drift = (Date.now() - lastPollTime.current) / 1000;
        setLocalElapsed(lastPollElapsed.current + drift);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [done, repoStatus, hasElapsed]);

  // Compute active step from backend progress or demo
  const activeStep = repoId
    ? done
      ? PIPELINE_STEPS.length
      : repoStatus === 'pending'
        ? 0
        : (progress?.current_step ?? 1) - 1 // backend is 1-indexed, UI is 0-indexed
    : done
      ? PIPELINE_STEPS.length
      : demoStep;

  const stepStates = getStepStates(Math.min(activeStep, PIPELINE_STEPS.length - 1));

  // Derive agent states for sub-stepper
  const agentStates = getAgentStates(agentEvents);
  const completedAgents = Object.values(agentStates).filter((a) => a.status === 'complete').length;

  // Interpolate progress bar within the active step using sub-progress data
  const pct = (() => {
    if (done) return 100;
    const totalSteps = PIPELINE_STEPS.length;
    const basePct = (activeStep / totalSteps) * 100;
    const stepSize = 100 / totalSteps;
    let subProgress = 0.5; // default: assume halfway through active step
    const s = progress?.stats;
    if (s) {
      if (activeStep === 4 && s.agents_total && s.agents_total > 0) {
        // Step 5 (0-indexed 4): facet agent progress
        subProgress = (s.agents_completed ?? 0) / s.agents_total;
      } else if (activeStep === 7) {
        // Step 8 (0-indexed 7): wiki agent progress
        if (completedAgents > 0 || Object.values(agentStates).some(a => a.status === 'running')) {
          subProgress = completedAgents / WIKI_AGENTS.length;
        } else if (s.pages_total && s.pages_total > 0) {
          // Fallback: page generation progress
          subProgress = (s.pages_generated ?? 0) / s.pages_total;
        } else {
          subProgress = 0.05; // Starting Step 8
        }
      }
    }
    return Math.min(99, Math.round(basePct + stepSize * subProgress));
  })();
  const displayName = repo?.name ?? name;
  const displayUrl = repo?.url ?? `github.com/${owner}/${name}`;
  const liveStats = buildLiveStats(progress?.stats);

  // ─── Error state ────────────────────────────────────────────────────────────
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
              &larr; Back
            </Link>
            <div style={{ marginLeft: 'auto' }}>
              <Logo href="/dashboard" size="sm" />
            </div>
          </div>

          <GlassCard
            style={{
              width: '100%',
              maxWidth: 700,
              padding: '48px 44px',
              textAlign: 'center',
            }}
            className="animate-fade-in-up"
          >
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

            <h1 style={{ fontSize: 28, fontWeight: 800, color: '#f87171', marginBottom: 12 }}>
              Analysis Failed
            </h1>

            {/* Show which step failed */}
            {progress?.step_label && (
              <p style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 8 }}>
                Failed at step {progress.current_step}: {progress.step_label}
              </p>
            )}

            <p style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Something went wrong while analyzing {displayName}.
            </p>

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

  // ─── Completion state ───────────────────────────────────────────────────────
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
              &larr; Back
            </Link>
            <div style={{ marginLeft: 'auto' }}>
              <Logo href="/dashboard" size="sm" />
            </div>
          </div>

          <GlassCard
            style={{
              width: '100%',
              maxWidth: 700,
              padding: '48px 44px',
              textAlign: 'center',
            }}
            className="animate-fade-in-up"
          >
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
              {'\u2728'}
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
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Your documentation has been generated successfully.
            </p>
            {progress?.elapsed_seconds != null && (
              <p style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 24 }}>
                Completed in {formatElapsed(progress.elapsed_seconds)}
              </p>
            )}

            {/* Final stats summary */}
            {liveStats.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  gap: 20,
                  flexWrap: 'wrap',
                  justifyContent: 'center',
                  padding: '16px 0',
                  borderTop: '1px solid var(--glass-border)',
                  marginBottom: 28,
                  fontSize: 13,
                }}
              >
                {liveStats.map((s) => (
                  <div
                    key={s.label}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-tertiary)' }}
                  >
                    {s.label}:{' '}
                    <span style={{ color: 'var(--primary-light)', fontWeight: 700 }}>{s.value}</span>
                  </div>
                ))}
              </div>
            )}

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
              View Wiki &rarr;
            </Link>
          </GlassCard>
        </div>
      </>
    );
  }

  // ─── Active analysis state ──────────────────────────────────────────────────
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

          {/* Vertical stepper — 9 real steps */}
          <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 40, position: 'relative' }}>
            {PIPELINE_STEPS.map((step, i) => {
              const state = stepStates[i];
              const isActive = state === 'active';
              const stepDetail = isActive ? progress?.step_detail : null;

              return (
                <div
                  key={step.label}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 16,
                    paddingBottom: i < PIPELINE_STEPS.length - 1 ? 24 : 0,
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
                    {state === 'complete' ? '\u2713' : i + 1}
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
                      <span style={{ fontSize: 14 }}>{step.icon}</span>
                      {step.label}
                      {isActive && (
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
                          isActive ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                        transition: 'all 0.3s',
                      }}
                    >
                      {state === 'complete'
                        ? 'Done'
                        : isActive
                        ? stepDetail || 'In progress\u2026'
                        : 'Pending'}
                    </div>

                    {/* Agent sub-stepper for Step 8 (wiki generation) */}
                    {i === 7 && (isActive || state === 'complete') && (
                      <div
                        style={{
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: 6,
                          marginTop: 10,
                        }}
                      >
                        {WIKI_AGENTS.map((agent) => {
                          const as = agentStates[agent.id];
                          const agentStatus = as?.status ?? 'pending';
                          const bg =
                            agentStatus === 'complete'
                              ? 'rgba(34,197,94,0.15)'
                              : agentStatus === 'running'
                              ? 'rgba(6,182,212,0.15)'
                              : 'rgba(255,255,255,0.04)';
                          const border =
                            agentStatus === 'complete'
                              ? 'rgba(34,197,94,0.4)'
                              : agentStatus === 'running'
                              ? 'rgba(6,182,212,0.4)'
                              : 'var(--glass-border)';
                          const color =
                            agentStatus === 'complete'
                              ? '#4ade80'
                              : agentStatus === 'running'
                              ? 'var(--secondary)'
                              : 'var(--text-tertiary)';

                          return (
                            <span
                              key={agent.id}
                              title={as?.detail || agent.desc}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 5,
                                padding: '3px 10px',
                                background: bg,
                                border: `1px solid ${border}`,
                                borderRadius: 12,
                                fontSize: 11,
                                fontWeight: 600,
                                color,
                                transition: 'all 0.3s',
                              }}
                            >
                              {agentStatus === 'complete' && (
                                <span style={{ fontSize: 10 }}>{'\u2713'}</span>
                              )}
                              {agentStatus === 'running' && (
                                <span
                                  style={{
                                    display: 'inline-block',
                                    width: 8,
                                    height: 8,
                                    border: '1.5px solid rgba(6,182,212,0.3)',
                                    borderTopColor: 'var(--secondary)',
                                    borderRadius: '50%',
                                    animation: 'spin 0.8s linear infinite',
                                  }}
                                />
                              )}
                              {agent.label}
                            </span>
                          );
                        })}
                      </div>
                    )}
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

          {/* Progress bar + elapsed time */}
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
                {localElapsed != null
                  ? formatElapsed(localElapsed)
                  : repoStatus === 'pending'
                  ? 'Waiting to start\u2026'
                  : ''}
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

          {/* Live stats panel — only shows stats that have arrived */}
          {liveStats.length > 0 && (
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
              {liveStats.map((s) => (
                <div
                  key={s.label}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    color: 'var(--text-tertiary)',
                    transition: 'opacity 0.3s',
                  }}
                >
                  {s.label}:{' '}
                  <span style={{ color: 'var(--primary-light)', fontWeight: 700 }}>{s.value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Languages detected */}
          {progress?.stats?.languages && progress.stats.languages.length > 0 && (
            <div
              style={{
                display: 'flex',
                gap: 8,
                flexWrap: 'wrap',
                marginBottom: 28,
              }}
            >
              {progress.stats.languages.map((lang) => (
                <span
                  key={lang}
                  style={{
                    padding: '4px 12px',
                    background: 'rgba(139,92,246,0.12)',
                    border: '1px solid rgba(139,92,246,0.25)',
                    borderRadius: 20,
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--primary-light)',
                  }}
                >
                  {lang}
                </span>
              ))}
            </div>
          )}

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

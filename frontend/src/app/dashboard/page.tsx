'use client';

/**
 * Dashboard — repository list with status badges matching dashboard.html mock.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/dashboard.html
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { api } from '@/services/api';

interface Repo {
  id: string;
  name: string;
  owner: string;
  url: string;
  status: string;
  primary_languages: string[];
  size_files: number | null;
  size_lines: number | null;
  last_analyzed_at: string | null;
}

export default function DashboardPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.repositories
      .list()
      .then((data) => setRepos(data.repositories as Repo[]))
      .catch(() => setRepos([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <GradientBackground />
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 24px' }}>
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 40,
          }}
          className="animate-fade-in-up"
        >
          <Logo href="/" />
          <Link href="/submit" className="btn-primary">
            + Add Repository
          </Link>
        </div>

        <h1
          style={{ fontSize: 32, fontWeight: 700, marginBottom: 8 }}
          className="animate-fade-in-up"
        >
          Your Repositories
        </h1>
        <p
          style={{ color: 'var(--text-secondary)', marginBottom: 40 }}
          className="animate-fade-in-up"
        >
          {repos.length} repositor{repos.length === 1 ? 'y' : 'ies'} indexed
        </p>

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 80 }}>
            Loading repositories…
          </div>
        )}

        {/* Empty state */}
        {!loading && repos.length === 0 && (
          <GlassCard
            style={{
              padding: 80,
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 24,
            }}
          >
            <div style={{ fontSize: 64 }}>📦</div>
            <h2 style={{ fontSize: 24, fontWeight: 700 }}>No repositories yet</h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: 400 }}>
              Add your first repository to start generating AI-powered documentation.
            </p>
            <Link href="/submit" className="btn-primary">
              + Add Repository
            </Link>
          </GlassCard>
        )}

        {/* Repo grid */}
        {!loading && repos.length > 0 && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: 24,
            }}
            className="stagger"
          >
            {repos.map((repo) => (
              <Link
                key={repo.id}
                href={`/${repo.owner}/${repo.name}`}
                style={{ textDecoration: 'none' }}
              >
                <GlassCard
                  className="animate-fade-in-up"
                  style={{
                    padding: 28,
                    cursor: 'pointer',
                    transition: 'all 0.3s cubic-bezier(0.4,0,0.2,1)',
                  }}
                  onMouseOver={(e: React.MouseEvent<HTMLDivElement>) => {
                    e.currentTarget.style.transform = 'translateY(-4px)';
                    e.currentTarget.style.borderColor = 'rgba(139,92,246,0.4)';
                    e.currentTarget.style.boxShadow = '0 12px 40px rgba(139,92,246,0.2)';
                  }}
                  onMouseOut={(e: React.MouseEvent<HTMLDivElement>) => {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.borderColor = 'var(--glass-border)';
                    e.currentTarget.style.boxShadow = 'var(--shadow-glass)';
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: 12,
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontFamily: "'Fira Code', monospace",
                          fontSize: 18,
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                        }}
                      >
                        {repo.owner}/{repo.name}
                      </div>
                    </div>
                    <StatusIndicator status={repo.status} />
                  </div>

                  {/* Languages */}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                    {(repo.primary_languages || []).slice(0, 4).map((lang) => (
                      <span key={lang} className="badge badge-primary" style={{ fontSize: 11 }}>
                        {lang}
                      </span>
                    ))}
                  </div>

                  {/* Stats row */}
                  <div
                    style={{
                      display: 'flex',
                      gap: 24,
                      fontSize: 13,
                      color: 'var(--text-tertiary)',
                      borderTop: '1px solid var(--glass-border)',
                      paddingTop: 16,
                    }}
                  >
                    {repo.size_files != null && (
                      <span>{repo.size_files.toLocaleString()} files</span>
                    )}
                    {repo.size_lines != null && (
                      <span>{repo.size_lines.toLocaleString()} LOC</span>
                    )}
                    {repo.last_analyzed_at && (
                      <span>
                        Updated{' '}
                        {new Date(repo.last_analyzed_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </GlassCard>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

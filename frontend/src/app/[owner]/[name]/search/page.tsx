'use client';

/**
 * Search page — hybrid keyword + semantic search.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/search.html
 */

import { useEffect, useState, useCallback } from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { GlassCard } from '@/components/ui/GlassCard';
import { Logo } from '@/components/ui/Logo';
import { TypeBadge } from '@/components/ui/TypeBadge';
import { api } from '@/services/api';
import type { SearchResultItem } from '@/services/api';

const TABS = [
  { value: 'all', label: 'All' },
  { value: 'entities', label: 'Functions' },
  { value: 'entities', label: 'Classes' },
  { value: 'modules', label: 'Modules' },
  { value: 'pages', label: 'Documentation' },
] as const;

const SORT_OPTIONS = ['Relevance', 'Name A–Z', 'Type'];

export default function SearchPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const owner = params.owner as string;
  const name = params.name as string;
  const base = `/${owner}/${name}`;

  const [query, setQuery] = useState(searchParams.get('q') ?? '');
  const [activeTab, setActiveTab] = useState(0);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState('Relevance');

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) { setResults([]); return; }
      setLoading(true);
      try {
        const { repositories } = await api.repositories.list();
        const repo = repositories.find(
          (r) => r.owner?.toLowerCase() === owner.toLowerCase() && r.name.toLowerCase() === name.toLowerCase()
        );
        if (!repo) return;
        const res = await api.search.query(repo.id, q);
        setResults(res.results);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [owner, name]
  );

  useEffect(() => {
    const q = searchParams.get('q') ?? '';
    setQuery(q);
    if (q) doSearch(q);
  }, [searchParams, doSearch]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(`${base}/search?q=${encodeURIComponent(query)}`);
  };

  const displayResults = results;

  return (
    <>
      <GradientBackground />
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px 80px' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
          <Logo href={base} />
          <Link href={base} style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-tertiary)', textDecoration: 'none' }}>
            ← Back to Wiki
          </Link>
        </div>

        {/* Search bar */}
        <form onSubmit={handleSearch} style={{ marginBottom: 24 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: 'var(--glass-bg)',
              backdropFilter: 'blur(20px)',
              border: '1px solid var(--glass-border)',
              borderRadius: 16,
              padding: '14px 20px',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
          >
            <span style={{ fontSize: 18 }}>🔍</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search functions, classes, modules, documentation…"
              autoFocus
              style={{
                flex: 1,
                background: 'none',
                border: 'none',
                outline: 'none',
                color: 'var(--text-primary)',
                fontFamily: "'Outfit', sans-serif",
                fontSize: 16,
              }}
            />
            {query && (
              <button
                type="button"
                onClick={() => { setQuery(''); setResults([]); }}
                style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', fontSize: 18 }}
              >
                ✕
              </button>
            )}
          </div>
        </form>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {TABS.map((tab, i) => (
            <button
              key={i}
              onClick={() => setActiveTab(i)}
              style={{
                padding: '8px 16px',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 600,
                fontFamily: "'Outfit', sans-serif",
                cursor: 'pointer',
                transition: 'all 0.2s',
                ...(activeTab === i
                  ? { background: 'rgba(139,92,246,0.2)', color: 'var(--primary-light)', border: '1px solid rgba(139,92,246,0.4)' }
                  : { background: 'rgba(255,255,255,0.05)', color: 'var(--text-tertiary)', border: '1px solid var(--glass-border)' }),
              }}
            >
              {tab.label}
            </button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Sort:</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: 8,
                color: 'var(--text-primary)',
                padding: '6px 10px',
                fontSize: 13,
                fontFamily: "'Outfit', sans-serif",
                cursor: 'pointer',
              }}
            >
              {SORT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        </div>

        {/* Results */}
        {loading ? (
          <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 60 }}>Searching…</div>
        ) : !query ? (
          <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 60 }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>🔍</div>
            <p>Enter a search term to find functions, classes, modules, and documentation.</p>
          </div>
        ) : (
          <>
            <p style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 16 }}>
              {displayResults.length} results for "<strong style={{ color: 'var(--text-primary)' }}>{query}</strong>"
            </p>
            {displayResults.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 60 }}>
                <div style={{ fontSize: 40, marginBottom: 16 }}>🔎</div>
                <p>No results found for "<strong style={{ color: 'var(--text-primary)' }}>{query}</strong>"</p>
                <p style={{ fontSize: 13, marginTop: 8 }}>Try a different search term or check that analysis has completed.</p>
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {displayResults.map((r) => (
                <Link
                  key={r.id}
                  href={r.type === 'entity' ? `${base}/entities/${encodeURIComponent(r.id)}` : r.type === 'module' ? `${base}/modules/${r.id}` : `${base}/${r.id}`}
                  style={{ textDecoration: 'none' }}
                >
                  <GlassCard
                    style={{ padding: '20px 24px', transition: 'all 0.2s' }}
                    onMouseOver={(e: React.MouseEvent<HTMLDivElement>) => {
                      e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)';
                      e.currentTarget.style.transform = 'translateY(-2px)';
                    }}
                    onMouseOut={(e: React.MouseEvent<HTMLDivElement>) => {
                      e.currentTarget.style.borderColor = 'var(--glass-border)';
                      e.currentTarget.style.transform = 'none';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                      <TypeBadge
                        type={r.type === 'entity' ? 'function' : r.type === 'module' ? 'module' : 'function'}
                        style={{ flexShrink: 0, marginTop: 2 }}
                      />
                      <div>
                        <div
                          style={{
                            fontFamily: "'Fira Code', monospace",
                            fontSize: 15,
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                            marginBottom: 6,
                          }}
                        >
                          {r.title}
                        </div>
                        {r.snippet && (
                          <p style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                            {r.snippet}
                          </p>
                        )}
                      </div>
                      <div style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-tertiary)', flexShrink: 0 }}>
                        {r.score ? `${Math.round(r.score * 100)}% match` : ''}
                      </div>
                    </div>
                  </GlassCard>
                </Link>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

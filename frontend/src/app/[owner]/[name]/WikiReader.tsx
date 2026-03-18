'use client';
// v2-improvements
import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { TypeBadge } from '@/components/ui/TypeBadge';
import { TableOfContents, type TocEntry } from '@/components/layout/TableOfContents';
import { WikiSidebar } from '@/components/layout/WikiSidebar';
import { api } from '@/services/api';
import type { Module, Repository, WikiPage } from '@/services/api';
import { MermaidDiagram, V2SectionContent, V2HomeContent, GettingStartedContent, GlossaryContent, ApiReferenceContent, FunctionIndexContent } from '@/components/wiki/V2Components';

interface WikiReaderProps {
  owner: string;
  name: string;
  slug?: string; // undefined = overview/home
}

function Breadcrumbs({ crumbs }: { crumbs: { label: string; href?: string }[] }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 13,
        color: 'var(--text-tertiary)',
        marginBottom: 8,
      }}
    >
      {crumbs.map((crumb, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span>/</span>}
          {crumb.href ? (
            <Link
              href={crumb.href}
              style={{
                color: 'inherit',
                textDecoration: 'none',
                transition: 'color 0.2s',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = 'var(--text-primary)')}
              onMouseOut={(e) => (e.currentTarget.style.color = 'inherit')}
            >
              {crumb.label}
            </Link>
          ) : (
            <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{crumb.label}</span>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

function Chip({ icon, label }: { icon: string; label: string }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 12px',
        background: 'rgba(255,255,255,0.05)',
        border: '1px solid var(--glass-border)',
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 500,
        color: 'var(--text-secondary)',
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function Logo({ href }: { href: string }) {
  return (
    <Link
      href={href}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        textDecoration: 'none',
        padding: '8px 0',
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 18,
          fontWeight: 800,
          color: 'white',
          boxShadow: '0 0 15px rgba(139,92,246,0.3)',
        }}
      >
        W
      </div>
      <span
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: 'var(--text-primary)',
          letterSpacing: '-0.02em',
        }}
      >
        code wiki
      </span>
    </Link>
  );
}

function HomeContent({
  repo,
  homePage,
  modules,
  base,
  owner,
  name,
}: {
  repo: Repository | null;
  homePage: WikiPage | null;
  modules: Module[];
  base: string;
  owner: string;
  name: string;
}) {
  const content = homePage?.content as Record<string, unknown> | null;
  const isV2 = content?.version === 2;
  const commitHash = (content?.commit_hash as string | null) || homePage?.commit_hash || null;
  const repoUrl = repo?.url || (repo ? `https://github.com/${repo.owner}/${repo.name}` : null);

  // ─── V2 Layout (Illustrated Story Book) ──────────────────────────────────
  if (isV2 && content) {
    return (
      <>
        <Breadcrumbs
          crumbs={[
            { label: 'dashboard', href: '/dashboard' },
            { label: `${name} wiki` },
          ]}
        />
        {/* Commit reference bar */}
        {commitHash && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-tertiary)', marginTop: 8, marginBottom: 0 }}>
            <span>Based on commit</span>
            {repoUrl ? (
              <a
                href={`${repoUrl}/tree/${commitHash}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontFamily: "'Fira Code', monospace", color: 'var(--primary-light)', textDecoration: 'none' }}
              >{commitHash.slice(0, 7)}</a>
            ) : (
              <span style={{ fontFamily: "'Fira Code', monospace", color: 'var(--primary-light)' }}>{commitHash.slice(0, 7)}</span>
            )}
          </div>
        )}
        <div style={{ marginTop: 16 }}>
          <V2HomeContent content={content} base={base} name={name} />
        </div>
      </>
    );
  }

  // ─── Legacy V1 Fallback ──────────────────────────────────────────────────
  const stats = content?.stats as Record<string, number> | null;
  const overview = content?.overview as Record<string, unknown> | null;

  const description =
    (overview?.project_description as string) ||
    (stats && modules.length > 0
      ? `This repository contains ${modules.length} module${modules.length !== 1 ? 's' : ''} with ${stats.functions ?? 0} functions and ${stats.classes ?? 0} classes across ${stats.files ?? 0} files.`
      : 'Auto-generated documentation from source code analysis.');

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki` },
        ]}
      />

      <h1
        id="overview"
        style={{
          fontSize: 32,
          fontWeight: 800,
          marginTop: 24,
          marginBottom: 8,
          letterSpacing: '-0.02em',
        }}
      >
        {repo?.name || name}
      </h1>

      {/* Meta chips */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        {repo?.primary_languages?.[0] && <Chip icon="⚡" label={repo.primary_languages[0]} />}
        {repo?.last_analyzed_at && (
          <Chip icon="🕒" label={`Updated ${new Date(repo.last_analyzed_at).toLocaleDateString()}`} />
        )}
        {repo?.size_files && <Chip icon="📁" label={`${repo.size_files.toLocaleString()} files`} />}
      </div>

      <div className="content-body">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 24, fontSize: 16 }}>
          {description}
        </p>
      </div>

      {/* Stats grid */}
      <h2 id="stats" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
        Stats
      </h2>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: 12,
          marginBottom: 36,
        }}
      >
        {[
          { value: stats?.modules ?? modules.length, label: 'Modules' },
          { value: stats?.functions ?? 0, label: 'Functions' },
          { value: stats?.classes ?? 0, label: 'Classes' },
          {
            value: repo?.size_lines
              ? `${(repo.size_lines / 1000).toFixed(1)}k`
              : stats?.loc
                ? `${(stats.loc / 1000).toFixed(1)}k`
                : '—',
            label: 'Lines of Code',
          },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              padding: '20px 16px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)',
              borderRadius: 14,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-primary)' }}>
              {s.value}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 500 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Modules grid */}
      <h2 id="modules" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
        Modules
      </h2>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 14,
        }}
      >
        {modules.map((mod) => (
          <Link
            key={mod.id}
            href={`${base}/${mod.slug}`}
            style={{
              display: 'block',
              padding: 20,
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)',
              borderRadius: 14,
              textDecoration: 'none',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = 'var(--glass-border)';
              e.currentTarget.style.transform = 'none';
            }}
          >
            <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
              {mod.name || mod.slug}
            </h3>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {mod.file_count ?? 0} files
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}

function SectionContent({
  slug,
  repo,
  activePage,
  activeModule,
  base,
  name,
  readingOrder,
}: {
  slug: string;
  repo: Repository | null;
  activePage: WikiPage | null;
  activeModule: Module | null;
  base: string;
  name: string;
  readingOrder: string[];
}) {
  const content = activePage?.content as Record<string, unknown> | null;
  const pageType = activePage?.page_type as string | undefined;
  const isV2 = content?.version === 2 || (pageType && ['getting_started', 'api_reference', 'function_index', 'glossary'].includes(pageType));

  // Compute read time from word count
  const wordCount = (() => {
    if (!content) return 0;
    const ss = content.section_summaries as Array<{ word_count: number }> | null;
    if (ss?.length) return ss.reduce((acc, s) => acc + (s.word_count || 0), 0);
    const segs = content.prose_segments as Array<{ type: string; content?: string }> | null;
    if (segs) {
      const text = segs.filter(s => s.type === 'text').map(s => s.content || '').join(' ');
      return text.split(/\s+/).filter(Boolean).length;
    }
    return 0;
  })();
  const readTime = wordCount > 0 ? Math.max(1, Math.ceil(wordCount / 200)) : null;

  // Prev / Next based on reading order
  const currentIdx = readingOrder.indexOf(slug);
  const prevSlug = currentIdx > 0 ? readingOrder[currentIdx - 1] : null;
  const nextSlug = currentIdx >= 0 && currentIdx < readingOrder.length - 1 ? readingOrder[currentIdx + 1] : null;

  // Share button
  const [copied, setCopied] = React.useState(false);
  const handleShare = () => {
    if (typeof window !== 'undefined') {
      navigator.clipboard.writeText(window.location.href).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }).catch(() => {});
    }
  };

  const repoUrl = repo?.url || (repo ? `https://github.com/${repo.owner}/${repo.name}` : undefined);

  const renderContent = () => {
    if (!isV2 || !content) {
      return (
        <div style={{ color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          <p>Content unavailable for this page.</p>
        </div>
      );
    }
    switch (pageType) {
      case 'getting_started':
        return <GettingStartedContent content={content} />;
      case 'glossary':
        return <GlossaryContent content={content} />;
      case 'api_reference':
        return <ApiReferenceContent content={content} repoUrl={repoUrl} />;
      case 'function_index':
        return <FunctionIndexContent content={content} repoUrl={repoUrl} />;
      default:
        return <V2SectionContent content={content} base={base} name={name} />;
    }
  };

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: activePage?.title || activeModule?.name || slug },
        ]}
      />

      {/* Title + meta row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginTop: 24, marginBottom: 8, flexWrap: 'wrap' }}>
        <h1
          style={{
            fontSize: 32,
            fontWeight: 800,
            margin: 0,
            letterSpacing: '-0.02em',
            flex: 1,
          }}
        >
          {activePage?.title || activeModule?.name || slug}
        </h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, paddingTop: 6 }}>
          {readTime && (
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)', background: 'rgba(255,255,255,0.06)', padding: '4px 10px', borderRadius: 20 }}>
              ~{readTime} min read
            </span>
          )}
          <button
            onClick={handleShare}
            title="Copy link"
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid var(--glass-border)',
              borderRadius: 8,
              padding: '5px 12px',
              fontSize: 12,
              color: copied ? 'var(--success)' : 'var(--text-tertiary)',
              cursor: 'pointer',
              transition: 'all 0.2s',
              fontFamily: "'Outfit', sans-serif",
            }}
          >
            {copied ? '✓ Copied' : '🔗 Share'}
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 24 }}>
        {renderContent()}
      </div>

      {/* Prev / Next */}
      {(prevSlug || nextSlug) && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          marginTop: 48,
          paddingTop: 24,
          borderTop: '1px solid var(--glass-border)',
        }}>
          {prevSlug ? (
            <Link href={`${base}/${prevSlug}`} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '12px 20px', background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)', borderRadius: 12,
              textDecoration: 'none', color: 'var(--text-secondary)', fontSize: 14, fontWeight: 500,
              transition: 'all 0.2s', maxWidth: '48%',
            }}
              onMouseOver={e => { e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--glass-border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
            >
              <span>←</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{prevSlug}</span>
            </Link>
          ) : <div />}
          {nextSlug ? (
            <Link href={`${base}/${nextSlug}`} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '12px 20px', background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)', borderRadius: 12,
              textDecoration: 'none', color: 'var(--text-secondary)', fontSize: 14, fontWeight: 500,
              transition: 'all 0.2s', maxWidth: '48%', justifyContent: 'flex-end',
            }}
              onMouseOver={e => { e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--glass-border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nextSlug}</span>
              <span>→</span>
            </Link>
          ) : <div />}
        </div>
      )}
    </>
  );
}

export default function WikiReader({ owner, name, slug }: WikiReaderProps) {
  const router = useRouter();
  const base = `/${owner}/${name}`;
  const isHome = !slug || slug === 'home';

  const [repo, setRepo] = useState<Repository | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [homePage, setHomePage] = useState<WikiPage | null>(null);
  const [activePage, setActivePage] = useState<WikiPage | null>(null);
  const [activeModule, setActiveModule] = useState<Module | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('wiki-theme') as 'dark' | 'light' | null : null;
    if (saved) setTheme(saved);
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('wiki-theme', theme);
    }
  }, [theme]);

  useEffect(() => {
    const load = async () => {
      try {
        const { repositories } = await api.repositories.list();
        const found = repositories.find(
          (r) =>
            r.owner?.toLowerCase() === owner.toLowerCase() &&
            r.name.toLowerCase() === name.toLowerCase()
        );
        if (!found) {
          setLoading(false);
          return;
        }
        setRepo(found);

        const [mods, home] = await Promise.all([
          api.wikis.listModules(found.id).catch(() => []),
          api.wikis.getPage(found.id, 'home').catch(() => null),
        ]);
        setModules(mods);
        setHomePage(home);

        // Load active page if slug is set
        if (slug && slug !== 'home') {
          const [page, mod] = await Promise.all([
            api.wikis.getPage(found.id, slug).catch(() => null),
            api.wikis.getModule(found.id, slug).catch(() => null),
          ]);
          setActivePage(page);
          setActiveModule(mod);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [owner, name, slug]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`${base}/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  // Deduplicate modules by slug
  const uniqueModules = modules.filter(
    (m, i, arr) => arr.findIndex((x) => x.slug === m.slug) === i
  );

  // Derive reading order from home page section_summaries (pipeline order)
  const readingOrder: string[] = React.useMemo(() => {
    const homeContent = homePage?.content as Record<string, unknown> | null;
    const ss = homeContent?.section_summaries as Array<{ id: string }> | null;
    if (ss && ss.length > 0) return ss.map(s => s.id);
    const ro = homeContent?.suggested_reading_order as string[] | null;
    if (ro && ro.length > 0) return ro;
    return uniqueModules.map(m => m.slug);
  }, [homePage, uniqueModules]);

  // Sort modules by reading order
  const orderedModules = React.useMemo(() => {
    if (readingOrder.length === 0) return uniqueModules;
    const orderMap = new Map(readingOrder.map((slug, i) => [slug, i]));
    return [...uniqueModules].sort((a, b) => {
      const ai = orderMap.has(a.slug) ? orderMap.get(a.slug)! : 9999;
      const bi = orderMap.has(b.slug) ? orderMap.get(b.slug)! : 9999;
      return ai - bi;
    });
  }, [uniqueModules, readingOrder]);

  // Build sidebar sections
  const sidebarSections = [
    {
      label: 'Overview',
      items: [
        { label: 'Home', href: '', active: isHome, badge: undefined as string | undefined },
        { label: 'Getting Started', href: 'getting-started', active: slug === 'getting-started', badge: undefined },
      ],
    },
    ...(orderedModules.length > 0
      ? [
          {
            label: 'Modules',
            items: orderedModules.map((m, i) => ({
              label: m.name || m.slug || '/',
              href: m.slug,
              active: slug === m.slug,
              badge: readingOrder.length > 0 ? String(i + 1) : undefined,
            })),
          },
        ]
      : []),
    {
      label: 'Reference',
      items: [
        { label: 'API Reference', href: 'api-reference', active: slug === 'api-reference', badge: undefined as string | undefined },
        { label: 'Function Index', href: 'function-index', active: slug === 'function-index', badge: undefined },
        { label: 'Glossary', href: 'glossary', active: slug === 'glossary', badge: undefined },
      ],
    },
  ];

  // Build TOC entries
  const tocEntries: TocEntry[] = (() => {
    if (isHome) {
      return [
        { id: 'overview', label: 'Overview', level: 2 },
        { id: 'architecture-overview', label: 'Architecture', level: 2 },
        { id: 'stats', label: 'Stats', level: 2 },
        { id: 'sections', label: 'Modules', level: 2 },
      ];
    }
    const content = activePage?.content as Record<string, any>;
    if (!content || !content.prose_segments) return [];
    
    const items: TocEntry[] = [];
    const segments = content.prose_segments as any[];
    for (const seg of segments) {
      if (seg.type === 'heading') {
        const anchorId = (seg.text || '')
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-|-$/g, '');
        items.push({ id: anchorId, label: seg.text, level: seg.level || 2 });
      }
    }
    return items;
  })();

  return (
    <>
      <div
        className="wiki-layout"
        style={{
          display: 'grid',
          gridTemplateColumns: '300px 1fr 280px',
          minHeight: '100vh',
          gap: 0,
        }}
      >
        {/* ── Left sidebar ── */}
        <WikiSidebar pageTitle={`${name} Wiki`} width={300}>
          <div style={{ padding: '0 20px 12px' }}>
            <Logo href={base} />
          </div>

          {/* Search */}
          <div style={{ padding: '0 16px 16px' }}>
            <form
              onSubmit={handleSearch}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: 10,
                padding: '8px 12px',
              }}
            >
              <span style={{ fontSize: 14, color: 'var(--text-tertiary)' }}>🔍</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search…"
                style={{
                  flex: 1,
                  background: 'none',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--text-primary)',
                  fontFamily: "'Outfit', sans-serif",
                  fontSize: 13,
                }}
              />
            </form>
          </div>

          {sidebarSections.map((section) => (
            <div key={section.label} style={{ marginBottom: 8 }}>
              <div
                style={{
                  padding: '6px 20px',
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.8px',
                  color: 'var(--text-tertiary)',
                }}
              >
                {section.label}
              </div>
              <div>
                {section.items.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href ? `${base}/${item.href}` : base}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 20px',
                      fontSize: 14,
                      fontWeight: 500,
                      textDecoration: 'none',
                      color: item.active ? 'var(--primary-light)' : 'var(--text-secondary)',
                      background: item.active
                        ? 'linear-gradient(135deg, rgba(139,92,246,0.15), rgba(6,182,212,0.1))'
                        : 'transparent',
                      borderLeft: item.active
                        ? '3px solid var(--primary)'
                        : '3px solid transparent',
                      transition: 'all 0.2s',
                    }}
                  >
                    {item.badge && (
                      <span style={{
                        minWidth: 20, height: 20, borderRadius: '50%',
                        background: item.active ? 'var(--primary)' : 'rgba(255,255,255,0.1)',
                        color: item.active ? '#fff' : 'var(--text-tertiary)',
                        fontSize: 10, fontWeight: 700,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>{item.badge}</span>
                    )}
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}

          {/* App links */}
          <div style={{ marginTop: 16, borderTop: '1px solid var(--glass-border)', paddingTop: 12 }}>
            {[
              { label: '💬 AI Chat', href: `${base}/chat` },
              { label: '📊 Dashboard', href: '/dashboard' },
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '8px 20px',
                  fontSize: 14,
                  fontWeight: 500,
                  textDecoration: 'none',
                  color: 'var(--text-secondary)',
                  borderLeft: '3px solid transparent',
                  transition: 'all 0.2s',
                }}
              >
                {link.label}
              </Link>
            ))}
            {/* Theme toggle */}
            <button
              onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                width: '100%', padding: '8px 20px',
                background: 'none', border: 'none',
                cursor: 'pointer', fontSize: 14, fontWeight: 500,
                color: 'var(--text-secondary)', textAlign: 'left',
                fontFamily: "'Outfit', sans-serif",
                transition: 'color 0.2s',
              }}
              onMouseOver={e => e.currentTarget.style.color = 'var(--text-primary)'}
              onMouseOut={e => e.currentTarget.style.color = 'var(--text-secondary)'}
            >
              {theme === 'dark' ? '☀️ Light mode' : '🌙 Dark mode'}
            </button>
          </div>
        </WikiSidebar>

        {/* ── Main content ── */}
        <main
          className="wiki-main"
          style={{
            padding: '32px 40px',
            minWidth: 0,
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            borderRight: '1px solid var(--glass-border)',
          }}
        >
          {loading ? (
            <div style={{ color: 'var(--text-tertiary)', padding: '40px 0' }}>Loading…</div>
          ) : isHome ? (
            <HomeContent
              repo={repo}
              homePage={homePage}
              modules={uniqueModules}
              base={base}
              owner={owner}
              name={name}
            />
          ) : (
            <SectionContent
              slug={slug!}
              repo={repo}
              activePage={activePage}
              activeModule={activeModule}
              base={base}
              name={name}
              readingOrder={readingOrder}
            />
          )}
        </main>

        {/* ── Right TOC ── */}
        <aside
          style={{
            position: 'sticky',
            top: 0,
            height: '100vh',
            overflowY: 'auto',
            padding: '32px 20px',
          }}
        >
          <TableOfContents entries={tocEntries} />
        </aside>
      </div>

      <style jsx global>{`
        .wiki-layout {
          background: #0a0a12;
          color: var(--text-primary);
        }
        .v2-prose h2, .v2-prose h3 {
          scroll-margin-top: 32px;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </>
  );
}

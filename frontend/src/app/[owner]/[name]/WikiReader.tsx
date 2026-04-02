'use client';
// v2-improvements
import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { TableOfContents, type TocEntry } from '@/components/layout/TableOfContents';
import { WikiSidebar } from '@/components/layout/WikiSidebar';
import { api } from '@/services/api';
import type { Module, Repository, WikiPage } from '@/services/api';
import { V2SectionContent, V2HomeContent, GettingStartedContent, GlossaryContent, ApiReferenceContent, FunctionIndexContent, ProseRenderer, type ProseSegment } from '@/components/wiki/V2Components';

interface WikiReaderProps {
  owner: string;
  name: string;
  slug?: string; // undefined = overview/home
}

type SidebarLeafItem = {
  label: string;
  href: string;
  active: boolean;
  badge?: string;
  hint?: string;
  menuGroup?: string;
  menuLabel?: string;
};

type SidebarGroupItem = {
  label: string;
  active: boolean;
  children: SidebarLeafItem[];
};

type SidebarItem = SidebarLeafItem | SidebarGroupItem;

type SidebarSection = {
  label: string;
  items: SidebarItem[];
};

function isSidebarGroupItem(item: SidebarItem): item is SidebarGroupItem {
  return 'children' in item;
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
  name,
}: {
  repo: Repository | null;
  homePage: WikiPage | null;
  modules: Module[];
  base: string;
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
  allModules,
  base,
  name,
  readingOrder,
}: {
  slug: string;
  repo: Repository | null;
  activePage: WikiPage | null;
  activeModule: Module | null;
  allModules: Module[];
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

  // Prev / Next split by IA stream (learning vs reference)
  const learningOrder = React.useMemo(() => {
    const ordered = ['getting-started', ...readingOrder];
    return ordered.filter((value, index, arr) => arr.indexOf(value) === index);
  }, [readingOrder]);
  const referenceOrder = ['api-reference', 'function-index', 'glossary'];
  const activeStreamOrder = referenceOrder.includes(slug) ? referenceOrder : learningOrder;
  const currentIdx = activeStreamOrder.indexOf(slug);
  const prevSlug = currentIdx > 0 ? activeStreamOrder[currentIdx - 1] : null;
  const nextSlug = currentIdx >= 0 && currentIdx < activeStreamOrder.length - 1 ? activeStreamOrder[currentIdx + 1] : null;

  const SPECIAL_PAGE_TITLES: Record<string, string> = {
    'getting-started': 'Getting Started',
    'glossary': 'Glossary',
    'api-reference': 'API Reference',
    'function-index': 'Function Index',
  };
  const getPageTitle = (s: string) =>
    allModules.find(m => m.slug === s)?.name ??
    SPECIAL_PAGE_TITLES[s] ??
    s.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

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
        if (Array.isArray(content.terms)) {
          return <GlossaryContent content={content} />;
        }
        return <ProseRenderer segments={(content.prose_segments as ProseSegment[]) || []} base={base} />;
      case 'api_reference':
        if (content.index && typeof content.index === 'object') {
          return <ApiReferenceContent content={content} repoUrl={repoUrl} pageCommitHash={activePage?.commit_hash} />;
        }
        return <ProseRenderer segments={(content.prose_segments as ProseSegment[]) || []} base={base} />;
      case 'function_index':
        if (content.index && typeof content.index === 'object') {
          return <FunctionIndexContent content={content} repoUrl={repoUrl} pageCommitHash={activePage?.commit_hash} />;
        }
        return <ProseRenderer segments={(content.prose_segments as ProseSegment[]) || []} base={base} />;
      default:
        return <V2SectionContent content={content} base={base} name={name} activeModule={activeModule} allModules={allModules} />;
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
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{getPageTitle(prevSlug)}</span>
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
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{getPageTitle(nextSlug)}</span>
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
  const pageType = activePage?.page_type as string | undefined;

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
          const SPECIAL_PAGE_SLUGS = new Set(['getting-started', 'glossary', 'api-reference', 'function-index']);
          const [page, mod] = await Promise.all([
            api.wikis.getPage(found.id, slug).catch(() => null),
            SPECIAL_PAGE_SLUGS.has(slug) ? Promise.resolve(null) : api.wikis.getModule(found.id, slug).catch(() => null),
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
    (m, i, arr) =>
      arr.findIndex((x) => x.slug === m.slug) === i &&
      (m.slug || '').toLowerCase() !== 'home'
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

  const learningPathItems: SidebarLeafItem[] = React.useMemo(() => {
    const homeContent = homePage?.content as Record<string, unknown> | null;
    const summaries = Array.isArray(homeContent?.section_summaries)
      ? (homeContent?.section_summaries as Array<Record<string, unknown>>)
      : [];
    const summaryById = new Map(summaries.map((s) => [String(s.id || ''), s]));
    return orderedModules.map((m, i) => {
      const summary = summaryById.get(m.slug);
      const menuGroup = summary && typeof summary.menu_group === 'string' ? summary.menu_group : '';
      const menuLabel = summary && typeof summary.menu_label === 'string' ? summary.menu_label : '';
      return {
        label: m.name || m.slug || '/',
        href: m.slug,
        active: slug === m.slug,
        badge: readingOrder.length > 0 ? String(i + 1) : undefined,
        hint: i === 0 ? 'Start here' : undefined,
        menuGroup: menuGroup || undefined,
        menuLabel: menuLabel || undefined,
      };
    });
  }, [orderedModules, readingOrder, slug, homePage]);

  // Planner-driven grouping via home.content.section_summaries[].menu_group.
  // Falls back to flat list when no groups are provided.
  const groupedLearningPathItems: SidebarItem[] = React.useMemo(() => {
    const groupMeta = new Map<string, { firstIndex: number; children: SidebarLeafItem[] }>();
    const flatItems: SidebarLeafItem[] = [];

    learningPathItems.forEach((item, index) => {
      if (item.menuGroup) {
        const current = groupMeta.get(item.menuGroup);
        const child = {
          ...item,
          label: item.menuLabel || item.label,
        };
        if (current) {
          current.children.push(child);
        } else {
          groupMeta.set(item.menuGroup, { firstIndex: index, children: [child] });
        }
      } else {
        flatItems.push(item);
      }
    });

    if (groupMeta.size === 0) return learningPathItems;

    const groups = Array.from(groupMeta.entries()).sort((a, b) => a[1].firstIndex - b[1].firstIndex);
    const items: SidebarItem[] = [];
    let flatCursor = 0;

    for (const [groupLabel, data] of groups) {
      while (
        flatCursor < flatItems.length &&
        learningPathItems.findIndex((item) => item.href === flatItems[flatCursor].href) < data.firstIndex
      ) {
        items.push(flatItems[flatCursor]);
        flatCursor += 1;
      }
      items.push({
        label: groupLabel,
        active: data.children.some((child) => child.active),
        children: data.children,
      });
    }

    while (flatCursor < flatItems.length) {
      items.push(flatItems[flatCursor]);
      flatCursor += 1;
    }
 
    const seen = new Set<string>();
    return items.filter((it) => {
      const key = isSidebarGroupItem(it) ? `group:${it.label}` : `leaf:${it.href}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [learningPathItems]);

  const renderSidebarLeafItem = (item: SidebarLeafItem, paddingLeft = 20) => (
    <Link
      key={item.href}
      href={item.href ? `${base}/${item.href}` : base}
      aria-current={item.active ? 'page' : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: `8px 20px 8px ${paddingLeft}px`,
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
      <span
        title={item.label}
        style={{
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          lineHeight: 1.2,
          flex: 1,
          minWidth: 0,
        }}
      >
        {item.label}
      </span>
      {item.hint && (
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
            color: 'var(--primary-light)',
            background: 'rgba(139,92,246,0.15)',
            border: '1px solid rgba(139,92,246,0.25)',
            borderRadius: 999,
            padding: '2px 6px',
            flexShrink: 0,
          }}
        >
          {item.hint}
        </span>
      )}
    </Link>
  );

  // Build sidebar sections
  const sidebarSections: SidebarSection[] = [
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
            label: 'Learning Path',
            items: groupedLearningPathItems,
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
        ...(homePage?.content && (homePage.content as Record<string, unknown>).system_context_diagram
          ? [{ id: 'system-context', label: 'System Context', level: 2 as const }]
          : []),
        { id: 'architecture-overview', label: 'Architecture', level: 2 },
        { id: 'stats', label: 'Stats', level: 2 },
        { id: 'sections', label: 'Learning Path', level: 2 },
      ];
    }
    const content = activePage?.content as Record<string, unknown> | null;
    if (!content) return [];

    if (pageType === 'getting_started') {
      const items: TocEntry[] = [];
      if (Array.isArray(content.prerequisites) && content.prerequisites.length > 0) {
        items.push({ id: 'prerequisites', label: 'Prerequisites', level: 2 });
      }
      if (Array.isArray(content.setup_steps) && content.setup_steps.length > 0) {
        items.push({ id: 'setup', label: 'Setup Steps', level: 2 });
      }
      if (Array.isArray(content.configuration) && content.configuration.length > 0) {
        items.push({ id: 'configuration', label: 'Configuration', level: 2 });
      }
      if (Array.isArray(content.quick_links) && content.quick_links.length > 0) {
        items.push({ id: 'quick-links', label: 'Quick Links', level: 2 });
      }
      return items;
    }

    if (pageType === 'api_reference' || pageType === 'function_index') {
      const index = content.index as Record<string, unknown[]> | undefined;
      if (!index || typeof index !== 'object') return [];
      const letters = Object.keys(index).sort().slice(0, 60);
      return letters.map((letter) => ({
        id: `letter-${letter}`,
        label: letter,
        level: 2,
      }));
    }

    if (pageType === 'glossary') {
      const terms = Array.isArray(content.terms)
        ? (content.terms as Array<{ term?: string }>)
        : [];
      const letters = Array.from(
        new Set(
          terms
            .map((t) => (t.term || '').trim().charAt(0).toUpperCase())
            .filter((v) => /^[A-Z0-9]$/.test(v))
        )
      )
        .sort()
        .slice(0, 60);
      return letters.map((letter) => ({
        id: `letter-${letter}`,
        label: letter,
        level: 2,
      }));
    }

    if (!Array.isArray(content.prose_segments)) return [];
    const items: TocEntry[] = [];
    const segments = content.prose_segments as Array<{ type?: string; text?: string; level?: number }>;
    for (const seg of segments) {
      if (seg.type === 'heading') {
        const anchorId = (seg.text || '')
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-|-$/g, '');
        items.push({ id: anchorId, label: seg.text || anchorId, level: seg.level || 2 });
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
                {section.items.map((item) =>
                  isSidebarGroupItem(item) ? (
                    <div key={`group-${item.label}`} style={{ margin: '4px 0 8px' }}>
                      <div
                        style={{
                          padding: '8px 20px 8px 32px',
                          fontSize: 12,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.6px',
                          color: item.active ? 'var(--primary-light)' : 'var(--text-tertiary)',
                        }}
                      >
                        {item.label}
                      </div>
                      {item.children.map((child) => renderSidebarLeafItem(child, 44))}
                    </div>
                  ) : (
                    renderSidebarLeafItem(item, 20)
                  )
                )}
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
              name={name}
            />
          ) : (
            <SectionContent
              slug={slug!}
              repo={repo}
              activePage={activePage}
              activeModule={activeModule}
              allModules={uniqueModules}
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
          background: var(--bg-dark);
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

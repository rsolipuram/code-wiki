'use client';

/**
 * WikiReader — unified 3-column wiki layout.
 * All wiki content (overview, modules, getting started, glossary, API reference)
 * renders through this single component. Sidebar drives navigation.
 *
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { Logo } from '@/components/ui/Logo';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { InfoBox } from '@/components/ui/InfoBox';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { TypeBadge } from '@/components/ui/TypeBadge';
import { TableOfContents, type TocEntry } from '@/components/layout/TableOfContents';
import { WikiSidebar } from '@/components/layout/WikiSidebar';
import { api } from '@/services/api';
import type { Module, Repository, WikiPage } from '@/services/api';

interface WikiReaderProps {
  owner: string;
  name: string;
  slug?: string; // undefined = overview/home
}

function shortName(qualifiedName: string): string {
  const parts = qualifiedName.split('.');
  const last = parts[parts.length - 1] || qualifiedName;
  // Avoid truncating to just a file extension like "ts", "py", "js"
  if (last.length <= 3 && parts.length >= 2) {
    return parts.slice(-2).join('.');
  }
  return last;
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

  // Build sidebar sections
  const sidebarSections = [
    {
      label: 'Overview',
      items: [{ label: 'Home', href: '', active: isHome }],
    },
    ...(uniqueModules.length > 0
      ? [
          {
            label: 'Modules',
            items: uniqueModules.map((m) => ({
              label: m.name || m.slug || '/',
              href: m.slug,
              active: slug === m.slug,
            })),
          },
        ]
      : []),
    {
      label: 'Reference',
      items: [
        { label: 'Getting Started', href: 'getting-started', active: slug === 'getting-started' },
        { label: 'API Reference', href: 'api-reference', active: slug === 'api-reference' },
        { label: 'Function Index', href: 'function-index', active: slug === 'function-index' },
        { label: 'Glossary', href: 'glossary', active: slug === 'glossary' },
      ],
    },
  ];

  return (
    <>
      <GradientBackground />
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
                    {item.label}
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
          <TableOfContents items={getTocItems(isHome, slug)} />
        </aside>
      </div>
    </>
  );
}

// ─── Home / Overview content ────────────────────────────────────────────────

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
  const overview = content?.overview as Record<string, unknown> | null;
  const stats = content?.stats as Record<string, number> | null;
  const statsObj = content?.stats as Record<string, number> | null;
  const moduleList = (content?.module_list as { name: string }[]) ?? [];
  const description =
    (overview?.project_description as string) ||
    (statsObj && modules.length > 0
      ? `This repository contains ${modules.length} module${modules.length !== 1 ? 's' : ''} with ${statsObj.functions ?? 0} functions and ${statsObj.classes ?? 0} classes across ${statsObj.files ?? 0} files.`
      : overview?.name
        ? `Documentation for ${overview.name}`
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
        {repo?.primary_languages?.[0] && (
          <Chip icon="⚡" label={repo.primary_languages[0]} />
        )}
        {repo?.last_analyzed_at && (
          <Chip
            icon="🕒"
            label={`Updated ${new Date(repo.last_analyzed_at).toLocaleDateString()}`}
          />
        )}
        {repo?.size_files && (
          <Chip icon="📁" label={`${repo.size_files.toLocaleString()} files`} />
        )}
        {(overview?.system_type as string) && (
          <Chip icon="🏗️" label={overview!.system_type as string} />
        )}
      </div>

      <div className="content-body">
        <p
          style={{
            color: 'var(--text-secondary)',
            lineHeight: 1.8,
            marginBottom: 24,
            fontSize: 16,
          }}
        >
          {description}
        </p>
      </div>

      {/* ── Stats grid ── */}
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
            value: stats?.loc
              ? stats.loc > 1000
                ? `${(stats.loc / 1000).toFixed(1)}k`
                : stats.loc
              : repo?.size_lines
                ? `${(repo.size_lines / 1000).toFixed(1)}k`
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
            <div
              style={{
                fontSize: 28,
                fontWeight: 800,
                background: 'linear-gradient(135deg, var(--primary-light), var(--secondary))',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                marginBottom: 4,
              }}
            >
              {s.value}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 500 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* ── Module list ── */}
      <h2 id="modules" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
        Modules
      </h2>
      {modules.length > 0 ? (
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
              <h3
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  marginBottom: 6,
                }}
              >
                {mod.name}
              </h3>
              <p
                style={{
                  fontSize: 13,
                  color: 'var(--text-tertiary)',
                  lineHeight: 1.6,
                  marginBottom: 10,
                }}
              >
                {mod.description || 'No description available.'}
              </p>
              <div
                style={{
                  display: 'flex',
                  gap: 12,
                  fontSize: 12,
                  color: 'var(--text-tertiary)',
                  borderTop: '1px solid var(--glass-border)',
                  paddingTop: 10,
                }}
              >
                {mod.file_count != null && (
                  <span>
                    <strong style={{ color: 'var(--text-primary)' }}>{mod.file_count}</strong> files
                  </span>
                )}
                {mod.file_paths?.[0] && (
                  <span
                    style={{
                      fontFamily: "'Fira Code', monospace",
                      fontSize: 11,
                    }}
                  >
                    {mod.file_paths[0]}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p style={{ color: 'var(--text-tertiary)' }}>No modules detected yet.</p>
      )}
    </>
  );
}

// ─── Section content (module or special page) ───────────────────────────────

function SectionContent({
  slug,
  repo,
  activePage,
  activeModule,
  base,
  name,
}: {
  slug: string;
  repo: Repository | null;
  activePage: WikiPage | null;
  activeModule: Module | null;
  base: string;
  name: string;
}) {
  const content = activePage?.content as Record<string, unknown> | null;
  const overview = content?.overview as {
    purpose?: string;
    design_patterns?: string[];
    data_flow?: string;
  } | null;
  const keyComponents =
    (content?.key_components as { name: string; role: string }[] | null) ?? [];
  const deps = content?.dependencies as {
    internal?: string[];
    external?: string[];
  } | null;
  const howItWorks =
    (content?.how_it_works as string | null) ?? overview?.data_flow ?? null;
  const knownIssues = (content?.known_issues as string[] | null) ?? [];
  const relatedPages =
    (content?.related_pages as { name: string; slug: string }[] | null) ?? [];
  const commitHash = (content?.commit_hash as string | null) ?? null;

  const displayName = activeModule?.name
    ? activeModule.name
        .replace(/-/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase())
    : activePage?.title
      ? activePage.title
      : slug
          .replace(/-/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());

  const description =
    overview?.purpose ??
    activeModule?.description ??
    (content?.description as string) ??
    '';

  const filePaths = activeModule?.file_paths ?? [];
  const isModulePage = !!activeModule;

  // Dispatch to special page renderers based on page type
  const pageType = activePage?.page_type;
  if (pageType === 'getting_started' || slug === 'getting-started') {
    return <GettingStartedContent content={content} base={base} name={name} />;
  }
  if (pageType === 'glossary' || slug === 'glossary') {
    return <GlossaryContent content={content} base={base} name={name} />;
  }
  if (pageType === 'function_index' || slug === 'function-index') {
    return <FunctionIndexContent content={content} base={base} name={name} />;
  }
  if (pageType === 'api_reference' || slug === 'api-reference') {
    return <ApiReferenceContent content={content} base={base} name={name} />;
  }

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: displayName },
        ]}
      />

      <h1
        style={{
          fontSize: 32,
          fontWeight: 800,
          marginTop: 24,
          marginBottom: 8,
          letterSpacing: '-0.02em',
        }}
      >
        {displayName}
        {isModulePage && ' Module'}
      </h1>

      {/* Sync meta */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 13,
          color: 'var(--text-tertiary)',
          marginBottom: 24,
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--success)',
            display: 'inline-block',
            boxShadow: '0 0 6px var(--success)',
          }}
        />
        {commitHash && (
          <>
            <span>Commit:</span>
            <span
              style={{
                fontFamily: "'Fira Code', monospace",
                color: 'var(--primary-light)',
              }}
            >
              {commitHash.slice(0, 7)}
            </span>
            <span>·</span>
          </>
        )}
        <span>Auto-generated from source</span>
      </div>

      {description && (
        <div className="content-body">
          <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 24 }}>
            {description}
          </p>
        </div>
      )}

      {isModulePage && (
        <InfoBox variant="info">
          <strong>Auto-generated:</strong> This page is generated directly from source code in{' '}
          <code>{filePaths[0] ?? `${slug}/`}</code>. All function signatures, file sizes, and
          dependency data are extracted at analysis time and stay in sync with every commit.
        </InfoBox>
      )}

      {/* File Location */}
      {filePaths.length > 0 && (
        <>
          <h2 id="file-location" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            File Location
          </h2>
          <CodeBlock language="text">{filePaths.slice(0, 10).join('\n')}</CodeBlock>
        </>
      )}

      {/* Key Components */}
      {(keyComponents.length > 0 || isModulePage) && (
        <>
          <h2
            id="key-components"
            style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}
          >
            Key Components
          </h2>
          {keyComponents.length > 0 ? (
            <>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
                {keyComponents.length} key component{keyComponents.length !== 1 ? 's' : ''} in this
                module.
              </p>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: 16,
                  marginBottom: 8,
                }}
              >
                {keyComponents.map((comp) => (
                  <div
                    key={comp.name}
                    style={{
                      padding: 20,
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--glass-border)',
                      borderRadius: 14,
                      transition: 'border-color 0.2s',
                    }}
                  >
                    <TypeBadge type="function" style={{ marginBottom: 10 }} />
                    <div
                      style={{
                        fontFamily: "'Fira Code', monospace",
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--secondary)',
                        marginBottom: 8,
                        wordBreak: 'break-all',
                      }}
                    >
                      {shortName(comp.name)}
                    </div>
                    <p style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                      {comp.role}
                    </p>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p style={{ color: 'var(--text-tertiary)' }}>
              No components indexed for this module.
            </p>
          )}
        </>
      )}

      {/* Dependencies */}
      {deps && ((deps.internal?.length ?? 0) > 0 || (deps.external?.length ?? 0) > 0) && (
        <>
          <h2 id="dependencies" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Dependencies
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 8 }}>
            {[
              { title: 'Internal', items: deps.internal ?? [], color: 'var(--secondary)' },
              { title: 'External', items: deps.external ?? [], color: 'var(--primary-light)' },
            ].map((group) => (
              <div key={group.title}>
                <h3
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--text-tertiary)',
                    marginBottom: 10,
                  }}
                >
                  {group.title}
                </h3>
                {group.items.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {group.items.map((dep) => (
                      <span
                        key={dep}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '6px 12px',
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid var(--glass-border)',
                          borderRadius: 8,
                          fontSize: 12,
                          fontFamily: "'Fira Code', monospace",
                          color: group.color,
                        }}
                      >
                        {shortName(dep)}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>None</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* How It Works */}
      {howItWorks && (
        <>
          <h2 id="how-it-works" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            How It Works
          </h2>
          <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 16 }}>
            {howItWorks}
          </p>
          {overview?.design_patterns && overview.design_patterns.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {overview.design_patterns.map((p) => (
                <span
                  key={p}
                  style={{
                    padding: '4px 12px',
                    background: 'rgba(139,92,246,0.12)',
                    border: '1px solid rgba(139,92,246,0.25)',
                    borderRadius: 20,
                    fontSize: 12,
                    color: 'var(--primary-light)',
                  }}
                >
                  {p}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {/* Known Issues */}
      {knownIssues.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <InfoBox variant="warning">
            <strong>Known Issues:</strong>
            <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
              {knownIssues.map((issue, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {issue}
                </li>
              ))}
            </ul>
          </InfoBox>
        </div>
      )}

      {/* Related Pages */}
      {relatedPages.length > 0 && (
        <>
          <h2 id="related-pages" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Related Pages
          </h2>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {relatedPages.map((page) => (
              <Link
                key={page.slug}
                href={`${base}/${page.slug}`}
                style={{
                  padding: '8px 16px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 10,
                  fontSize: 13,
                  color: 'var(--secondary)',
                  textDecoration: 'none',
                  transition: 'border-color 0.2s',
                }}
              >
                {page.name}
              </Link>
            ))}
          </div>
        </>
      )}

      {/* Fallback for pages with no structured content */}
      {!activePage && !activeModule && (
        <InfoBox variant="info">
          No content found for <strong>{slug}</strong>. This section will be populated after the
          next analysis run.
        </InfoBox>
      )}
    </>
  );
}

// ─── TOC helper ──────────────────────────────────────────────────────────────

function getTocItems(isHome: boolean, slug?: string): TocEntry[] {
  if (isHome) {
    return [
      { id: 'overview', label: 'Overview', level: 2 },
      { id: 'stats', label: 'Stats', level: 2 },
      { id: 'modules', label: 'Modules', level: 2 },
    ];
  }
  switch (slug) {
    case 'getting-started':
      return [
        { id: 'prerequisites', label: 'Prerequisites', level: 2 },
        { id: 'setup', label: 'Setup Steps', level: 2 },
        { id: 'configuration', label: 'Configuration', level: 2 },
        { id: 'quick-links', label: 'Quick Links', level: 2 },
      ];
    case 'glossary':
      return [{ id: 'terms', label: 'Terms', level: 2 }];
    case 'function-index':
      return [{ id: 'index', label: 'Function Index', level: 2 }];
    case 'api-reference':
      return [{ id: 'index', label: 'API Index', level: 2 }];
    default:
      return [
        { id: 'file-location', label: 'File Location', level: 2 },
        { id: 'key-components', label: 'Key Components', level: 2 },
        { id: 'dependencies', label: 'Dependencies', level: 2 },
        { id: 'how-it-works', label: 'How It Works', level: 2 },
        { id: 'related-pages', label: 'Related Pages', level: 2 },
      ];
  }
}

// ─── Special page renderers ──────────────────────────────────────────────────

interface SpecialPageProps {
  content: Record<string, unknown> | null;
  base: string;
  name: string;
}

function GettingStartedContent({ content, base, name }: SpecialPageProps) {
  const prerequisites = (content?.prerequisites as { name: string; version: string; description: string }[]) ?? [];
  const setupSteps = (content?.setup_steps as { step: number; title: string; command?: string; description: string }[]) ?? [];
  const configuration = (content?.configuration as { key: string; description: string; required: boolean }[]) ?? [];
  const quickLinks = (content?.quick_links as { label: string; url: string }[]) ?? [];

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: 'Getting Started' },
        ]}
      />
      <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 24, marginBottom: 24, letterSpacing: '-0.02em' }}>
        Getting Started
      </h1>

      {prerequisites.length > 0 && (
        <>
          <h2 id="prerequisites" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Prerequisites
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {prerequisites.map((p) => (
              <div
                key={p.name}
                style={{
                  padding: '14px 18px',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span
                  style={{
                    padding: '4px 10px',
                    background: 'rgba(139,92,246,0.12)',
                    border: '1px solid rgba(139,92,246,0.25)',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 700,
                    fontFamily: "'Fira Code', monospace",
                    color: 'var(--primary-light)',
                  }}
                >
                  {p.name}
                </span>
                {p.version && p.version !== 'any' && (
                  <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: "'Fira Code', monospace" }}>
                    {p.version}
                  </span>
                )}
                {p.description && (
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{p.description}</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {setupSteps.length > 0 && (
        <>
          <h2 id="setup" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Setup Steps
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {setupSteps.map((s) => (
              <div key={s.step}>
                <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                  <span style={{ color: 'var(--secondary)', marginRight: 8 }}>{s.step}.</span>
                  {s.title}
                </h3>
                {s.command && <CodeBlock language="bash">{s.command}</CodeBlock>}
                {s.description && (
                  <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 8 }}>
                    {s.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {configuration.length > 0 && (
        <>
          <h2 id="configuration" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Configuration
          </h2>
          <div
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--glass-border)',
              borderRadius: 12,
              overflow: 'hidden',
            }}
          >
            {configuration.map((c, i) => (
              <div
                key={c.key}
                style={{
                  padding: '12px 18px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  borderBottom: i < configuration.length - 1 ? '1px solid var(--glass-border)' : 'none',
                }}
              >
                <code
                  style={{
                    fontFamily: "'Fira Code', monospace",
                    fontSize: 13,
                    color: 'var(--secondary)',
                    fontWeight: 600,
                  }}
                >
                  {c.key}
                </code>
                {c.required && (
                  <span style={{ fontSize: 10, fontWeight: 700, color: '#f59e0b', textTransform: 'uppercase' }}>
                    required
                  </span>
                )}
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>{c.description}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {quickLinks.length > 0 && (
        <>
          <h2 id="quick-links" style={{ fontSize: 22, fontWeight: 700, margin: '36px 0 16px' }}>
            Quick Links
          </h2>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {quickLinks.map((link) => (
              <a
                key={link.label}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  padding: '8px 16px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 10,
                  fontSize: 13,
                  color: 'var(--secondary)',
                  textDecoration: 'none',
                  transition: 'border-color 0.2s',
                }}
              >
                {link.label}
              </a>
            ))}
          </div>
        </>
      )}

      {!content && (
        <InfoBox variant="info">
          Getting started content will be available after the next analysis run.
        </InfoBox>
      )}
    </>
  );
}

function GlossaryContent({ content, base, name }: SpecialPageProps) {
  const terms = (content?.terms as { term: string; type: string; definition: string; related_terms: string[] }[]) ?? [];
  const totalCount = (content?.total_count as number) ?? terms.length;

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: 'Glossary' },
        ]}
      />
      <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 24, marginBottom: 8, letterSpacing: '-0.02em' }}>
        Glossary
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 32 }}>
        {totalCount} domain term{totalCount !== 1 ? 's' : ''} extracted from source code
      </p>

      {terms.length > 0 ? (
        <div id="terms" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {terms.map((t) => (
            <div
              key={t.term}
              style={{
                padding: '16px 20px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--glass-border)',
                borderRadius: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{t.term}</span>
                <TypeBadge type={t.type as 'function' | 'class' | 'method' | 'module'} style={{ fontSize: 10 }} />
              </div>
              <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 0 }}>
                {t.definition}
              </p>
              {t.related_terms?.length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                  {t.related_terms.map((rt) => (
                    <span
                      key={rt}
                      style={{
                        padding: '2px 8px',
                        background: 'rgba(6,182,212,0.1)',
                        borderRadius: 6,
                        fontSize: 11,
                        color: 'var(--secondary)',
                      }}
                    >
                      {rt}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <InfoBox variant="info">No glossary terms were extracted from this repository.</InfoBox>
      )}
    </>
  );
}

function FunctionIndexContent({ content, base, name }: SpecialPageProps) {
  const totalCount = (content?.total_count as number) ?? 0;
  const index = (content?.index as Record<string, { name: string; qualified_name: string; type: string; file: string; line: number; signature?: string; summary?: string }[]>) ?? {};
  const letters = Object.keys(index).sort();

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: 'Function Index' },
        ]}
      />
      <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 24, marginBottom: 8, letterSpacing: '-0.02em' }}>
        Function Index
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 16 }}>
        {totalCount} public entit{totalCount !== 1 ? 'ies' : 'y'} indexed
      </p>

      {/* Letter jump links */}
      {letters.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 28 }}>
          {letters.map((l) => (
            <a
              key={l}
              href={`#letter-${l}`}
              style={{
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 8,
                background: 'rgba(139,92,246,0.1)',
                border: '1px solid rgba(139,92,246,0.2)',
                fontSize: 13,
                fontWeight: 700,
                color: 'var(--primary-light)',
                textDecoration: 'none',
                fontFamily: "'Fira Code', monospace",
              }}
            >
              {l}
            </a>
          ))}
        </div>
      )}

      <div id="index" style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
        {letters.map((letter) => (
          <div key={letter} id={`letter-${letter}`}>
            <h3
              style={{
                fontSize: 20,
                fontWeight: 800,
                color: 'var(--primary-light)',
                borderBottom: '2px solid rgba(139,92,246,0.2)',
                paddingBottom: 8,
                marginBottom: 12,
              }}
            >
              {letter}
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {index[letter].map((entity) => (
                <div
                  key={entity.qualified_name}
                  style={{
                    padding: '10px 16px',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 10,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 12,
                  }}
                >
                  <TypeBadge type={entity.type as 'function' | 'class' | 'method'} />
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontFamily: "'Fira Code', monospace",
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--secondary)',
                        marginBottom: 4,
                      }}
                    >
                      {entity.name}
                      {entity.signature && (
                        <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>
                          {entity.signature.startsWith('(') ? entity.signature : `(${entity.signature})`}
                        </span>
                      )}
                    </div>
                    {entity.summary && (
                      <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: 0 }}>{entity.summary}</p>
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontFamily: "'Fira Code', monospace",
                      color: 'var(--text-tertiary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {entity.file}:{entity.line}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {letters.length === 0 && (
        <InfoBox variant="info">No public entities found to index.</InfoBox>
      )}
    </>
  );
}

function ApiReferenceContent({ content, base, name }: SpecialPageProps) {
  const totalCount = (content?.total_count as number) ?? 0;
  const index = (content?.index as Record<string, { name: string; qualified_name: string; type: string; file: string; line: number; signature?: string; description?: string }[]>) ?? {};
  const letters = Object.keys(index).sort();

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: 'dashboard', href: '/dashboard' },
          { label: `${name} wiki`, href: base },
          { label: 'API Reference' },
        ]}
      />
      <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 24, marginBottom: 8, letterSpacing: '-0.02em' }}>
        API Reference
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 16 }}>
        {totalCount} public API entit{totalCount !== 1 ? 'ies' : 'y'}
      </p>

      {/* Letter jump links */}
      {letters.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 28 }}>
          {letters.map((l) => (
            <a
              key={l}
              href={`#api-${l}`}
              style={{
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 8,
                background: 'rgba(6,182,212,0.1)',
                border: '1px solid rgba(6,182,212,0.2)',
                fontSize: 13,
                fontWeight: 700,
                color: 'var(--secondary)',
                textDecoration: 'none',
                fontFamily: "'Fira Code', monospace",
              }}
            >
              {l}
            </a>
          ))}
        </div>
      )}

      <div id="index" style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
        {letters.map((letter) => (
          <div key={letter} id={`api-${letter}`}>
            <h3
              style={{
                fontSize: 20,
                fontWeight: 800,
                color: 'var(--secondary)',
                borderBottom: '2px solid rgba(6,182,212,0.2)',
                paddingBottom: 8,
                marginBottom: 12,
              }}
            >
              {letter}
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {index[letter].map((entity) => (
                <div
                  key={entity.qualified_name}
                  style={{
                    padding: '14px 18px',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 10,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <TypeBadge type={entity.type as 'function' | 'class'} />
                    <span
                      style={{
                        fontFamily: "'Fira Code', monospace",
                        fontSize: 14,
                        fontWeight: 600,
                        color: 'var(--secondary)',
                      }}
                    >
                      {entity.name}
                    </span>
                    {entity.signature && (
                      <span
                        style={{
                          fontFamily: "'Fira Code', monospace",
                          fontSize: 12,
                          color: 'var(--text-tertiary)',
                        }}
                      >
                        {entity.signature}
                      </span>
                    )}
                  </div>
                  {entity.description && (
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: '0 0 6px' }}>
                      {entity.description}
                    </p>
                  )}
                  <span
                    style={{
                      fontSize: 11,
                      fontFamily: "'Fira Code', monospace",
                      color: 'var(--text-tertiary)',
                    }}
                  >
                    {entity.file}:{entity.line}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {letters.length === 0 && (
        <InfoBox variant="info">No public API entities found.</InfoBox>
      )}
    </>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function Chip({ icon, label }: { icon: string; label: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 12px',
        background: 'rgba(255,255,255,0.05)',
        border: '1px solid var(--glass-border)',
        borderRadius: 20,
        fontSize: 13,
        color: 'var(--text-tertiary)',
      }}
    >
      {icon} {label}
    </span>
  );
}

"use client";

/**
 * V2 wiki rendering components.
 *
 * Renders structured prose_segments from the V2 wiki pipeline:
 *   - text → <span>
 *   - source_link → <SourceLinkChip>
 *   - code_block → <EmbeddedCodeBlock>
 *   - section_link → <Link>
 *   - heading → <h2>/<h3> with anchor
 *
 * Also: MermaidDiagram, DataTable, V2HomeContent.
 */

import React, {
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
} from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { CodeBlock } from "@/components/ui/CodeBlock";

// ─── Types ──────────────────────────────────────────────────────────────────

export type ProseSegment = {
  type:
    | "text"
    | "source_link"
    | "code_block"
    | "section_link"
    | "heading"
    | "diagram"
    | "table";
  content?: string;
  name?: string;
  url?: string;
  code?: string;
  language?: string;
  file_path?: string;
  start_line?: number;
  slug?: string;
  title?: string;
  level?: number;
  text?: string;
  mermaid_source?: string;
  caption?: string;
  headers?: string[];
  rows?: string[][];
};

export type DiagramData = {
  mermaid_source: string;
  caption: string;
};

export type TableData = {
  headers: string[];
  rows: string[][];
  caption?: string;
};

export type SectionSummary = {
  id: string;
  title: string;
  word_count: number;
  diagram_count: number;
};

// ─── Sub-components ─────────────────────────────────────────────────────────

function SourceLinkChip({ name, url }: { name: string; url?: string }) {
  if (!url) {
    return (
      <span
        style={{
          padding: "2px 8px",
          background: "rgba(255,255,255,0.08)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 6,
          fontSize: "0.85em",
          fontFamily: "'Fira Code', monospace",
          color: "var(--text-secondary)",
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          verticalAlign: "middle",
          margin: "0 2px",
        }}
      >
        <span style={{ fontSize: 10, opacity: 0.6 }}>📦</span>
        {name}
      </span>
    );
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        padding: "2px 8px",
        background: "rgba(139,92,246,0.1)",
        border: "1px solid rgba(139,92,246,0.2)",
        borderRadius: 6,
        fontSize: "0.85em",
        fontFamily: "'Fira Code', monospace",
        color: "var(--primary-light)",
        textDecoration: "none",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        verticalAlign: "middle",
        margin: "0 2px",
        transition: "all 0.2s",
      }}
      onMouseOver={(e) => {
        e.currentTarget.style.background = "rgba(139,92,246,0.2)";
        e.currentTarget.style.borderColor = "rgba(139,92,246,0.4)";
      }}
      onMouseOut={(e) => {
        e.currentTarget.style.background = "rgba(139,92,246,0.1)";
        e.currentTarget.style.borderColor = "rgba(139,92,246,0.2)";
      }}
    >
      <span style={{ fontSize: 10, opacity: 0.8 }}>🔗</span>
      {name}
    </a>
  );
}

function EmbeddedCodeBlock({
  language,
  code,
  filePath,
  startLine,
}: {
  language: string;
  code: string;
  filePath?: string;
  startLine?: number;
}) {
  return (
    <div
      style={{
        margin: "24px 0",
        borderRadius: 12,
        overflow: "hidden",
        border: "1px solid var(--glass-border)",
        background: "rgba(0,0,0,0.2)",
      }}
    >
      {(filePath || language) && (
        <div
          style={{
            padding: "8px 16px",
            background: "rgba(255,255,255,0.03)",
            borderBottom: "1px solid var(--glass-border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: "var(--text-tertiary)",
              fontFamily: "'Fira Code', monospace",
            }}
          >
            {filePath
              ? `${filePath}${startLine ? `:${startLine}` : ""}`
              : language}
          </div>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-tertiary)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {language}
          </div>
        </div>
      )}
      <div style={{ padding: "4px 0" }}>
        <CodeBlock language={language} code={code} />
      </div>
    </div>
  );
}

// ─── DiagramExplorer ─────────────────────────────────────────────────────────

/**
 * DiagramExplorer — interactive modal for zooming and panning diagrams.
 */
function DiagramExplorer({
  svg,
  onClose,
  caption,
}: {
  svg: string;
  onClose: () => void;
  caption?: string;
}) {
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!svgRef.current || !svg) return;
    const parser = new DOMParser();
    const doc = parser.parseFromString(svg, "image/svg+xml");
    const svgElement = doc.documentElement;
    svgRef.current.replaceChildren();
    svgRef.current.appendChild(
      svgRef.current.ownerDocument.importNode(svgElement, true),
    );
  }, [svg]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY * -0.001;
    const newScale = Math.min(Math.max(0.1, transform.scale + delta), 10);
    setTransform((prev) => ({ ...prev, scale: newScale }));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setTransform((prev) => ({
      ...prev,
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    }));
  };

  const handleMouseUp = () => setIsDragging(false);

  const resetView = () => setTransform({ scale: 1, x: 0, y: 0 });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1000,
        background: "rgba(5, 5, 15, 0.95)",
        backdropFilter: "blur(10px)",
        display: "flex",
        flexDirection: "column",
        animation: "fadeIn 0.3s ease",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <div>
          <h3
            style={{ fontSize: 16, fontWeight: 600, color: "white", margin: 0 }}
          >
            Diagram Explorer
          </h3>
          {caption && (
            <p
              style={{
                fontSize: 13,
                color: "var(--text-tertiary)",
                margin: "4px 0 0",
              }}
            >
              {caption}
            </p>
          )}
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={resetView}
            style={{
              padding: "8px 16px",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "white",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Reset View
          </button>
          <button
            onClick={onClose}
            style={{
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              borderRadius: "50%",
              color: "#f87171",
              cursor: "pointer",
              fontSize: 20,
            }}
          >
            &times;
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{
          flex: 1,
          overflow: "hidden",
          cursor: isDragging ? "grabbing" : "grab",
          position: "relative",
          background: "#2d2d2d",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: `translate(-50%, -50%) translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            transition: isDragging ? "none" : "transform 0.1s ease-out",
            transformOrigin: "center center",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "80vw",
            height: "70vh",
          }}
        >
          <div ref={svgRef} style={{ width: "100%", height: "100%" }} />
        </div>

        {/* Controls Overlay */}
        <div
          style={{
            position: "absolute",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            background: "rgba(255,255,255,0.05)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 30,
            padding: "8px 24px",
            display: "flex",
            alignItems: "center",
            gap: 16,
            color: "var(--text-tertiary)",
            fontSize: 12,
            pointerEvents: "none",
          }}
        >
          <span>Scroll to Zoom</span>
          <span style={{ opacity: 0.3 }}>|</span>
          <span>Drag to Pan</span>
          <span style={{ opacity: 0.3 }}>|</span>
          <span>ESC to Close</span>
        </div>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .mermaid svg {
          max-width: none !important;
          height: auto !important;
        }
      `}</style>
    </div>
  );
}

/**
 * Renders a Mermaid diagram from source syntax.
 */
export function MermaidDiagram({
  source,
  caption,
}: {
  source: string;
  caption?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const [svgData, setSvgData] = useState<string>("");
  const [svgDataFull, setSvgDataFull] = useState<string>("");
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          themeVariables: {
            background: "#2d2d2d",
            // Node colors
            primaryColor: "#2d2d2d",
            primaryBorderColor: "#e2e8f0",
            primaryTextColor: "#e2e8f0",
            secondaryColor: "#2d2d2d",
            secondaryBorderColor: "#e2e8f0",
            secondaryTextColor: "#e2e8f0",
            tertiaryColor: "#2d2d2d",
            tertiaryBorderColor: "#e2e8f0",
            tertiaryTextColor: "#e2e8f0",
            // Edges
            lineColor: "#e2e8f0",
            edgeLabelBackground: "#2d2d2d",
            // Subgraphs / clusters
            clusterBkg: "#2d2d2d",
            clusterBorder: "#e2e8f0",
            titleColor: "#e2e8f0",
            // Color scale (auto-assigned palette) — force all to dark
            cScale0: "#2d2d2d",
            cScale1: "#2d2d2d",
            cScale2: "#2d2d2d",
            cScale3: "#2d2d2d",
            cScale4: "#2d2d2d",
            cScale5: "#2d2d2d",
            cScale6: "#2d2d2d",
            cScale7: "#2d2d2d",
            cScale8: "#2d2d2d",
            cScale9: "#2d2d2d",
            cScale10: "#2d2d2d",
            cScale11: "#2d2d2d",
            fontFamily: "Courier New, Courier, monospace",
          },
          flowchart: { curve: "linear" },
        });

        const id = `mermaid-${Math.random().toString(36).slice(2, 8)}`;
        const { svg } = await mermaid.render(id, source);
        if (!cancelled) {
          // Clean the SVG: normalize dimensions and strip LLM-injected fill colors.
          // Scope width/height replacements to the root <svg> tag only to avoid
          // clobbering <foreignObject> attributes.
          // Strip inline fill overrides (e.g. `style="fill:#e1f5fe !important"`)
          // that the LLM bakes into mermaid `style` directives — they beat our theme.
          const cleanedSvg = svg
            .replace(/(<svg\b[^>]*)\bwidth="[\d.]+"/, '$1width="100%"')
            .replace(/(<svg\b[^>]*)\bheight="[\d.]+"/, '$1height="100%"')
            .replace(/(<svg\b[^>]*)\bstyle="[^"]*max-width:[^"]*"/, "$1")
            // Remove !important fill/stroke overrides injected by LLM-authored mermaid
            // `style` directives (e.g. style="fill:#e1f5fe !important"). These beat
            // the theme CSS and produce unwanted colored nodes. Leave non-!important
            // values (set by theme CSS) untouched.
            .replace(/\bfill:\s*(?!none)[^;!]*!important/gi, "fill:#2d2d2d")
            .replace(
              /\bstroke:\s*(?!none)[^;!]*!important/gi,
              "stroke:#e2e8f0",
            );

          setSvgData(cleanedSvg);
          setSvgDataFull(svg);
          if (containerRef.current) {
            const parser = new DOMParser();
            const doc = parser.parseFromString(cleanedSvg, "image/svg+xml");
            const svgElement = doc.documentElement;
            containerRef.current.replaceChildren();
            containerRef.current.appendChild(
              containerRef.current.ownerDocument.importNode(svgElement, true),
            );
            setLoaded(true);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(`Diagram rendering failed: ${err}`);
        }
      }
    }

    renderDiagram();
    return () => {
      cancelled = true;
    };
  }, [source]);

  return (
    <>
      <div
        style={{
          margin: "24px 0",
          padding: 24,
          background: "#2d2d2d",
          border: "1px solid rgba(226,232,240,0.15)",
          borderRadius: 14,
          position: "relative",
          transition: "all 0.3s ease",
          cursor: loaded ? "pointer" : "default",
        }}
        onClick={() => loaded && setIsExpanded(true)}
        onMouseOver={(e) => {
          if (loaded) {
            e.currentTarget.style.background = "#353535";
            e.currentTarget.style.borderColor = "rgba(226,232,240,0.3)";
          }
        }}
        onMouseOut={(e) => {
          e.currentTarget.style.background = "#2d2d2d";
          e.currentTarget.style.borderColor = "rgba(226,232,240,0.15)";
        }}
      >
        {loaded && (
          <div
            style={{
              position: "absolute",
              top: 16,
              right: 16,
              zIndex: 10,
              padding: "6px 12px",
              background: "rgba(139,92,246,0.1)",
              border: "1px solid rgba(139,92,246,0.2)",
              borderRadius: 8,
              color: "var(--primary-light)",
              fontSize: 12,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
              pointerEvents: "none",
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 3 21 3 21 9" />
              <polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" />
              <line x1="3" y1="21" x2="10" y2="14" />
            </svg>
            Explore
          </div>
        )}

        {error ? (
          <div style={{ color: "var(--text-tertiary)", fontSize: 13 }}>
            {error}
          </div>
        ) : !loaded ? (
          <div style={{ color: "var(--text-tertiary)", fontSize: 13 }}>
            Loading diagram...
          </div>
        ) : null}

        <div
          ref={containerRef}
          style={{
            display: "flex",
            justifyContent: "center",
            overflow: "hidden",
            maxHeight: 400,
            pointerEvents: "none",
          }}
        />

        {caption && (
          <div
            style={{
              marginTop: 16,
              fontSize: 12,
              color: "var(--text-tertiary)",
              textAlign: "center",
              fontStyle: "italic",
              letterSpacing: "0.02em",
            }}
          >
            {caption}
          </div>
        )}
      </div>

      {isExpanded &&
        typeof document !== "undefined" &&
        createPortal(
          <DiagramExplorer
            svg={svgData}
            caption={caption}
            onClose={() => setIsExpanded(false)}
          />,
          document.body,
        )}
    </>
  );
}

// ─── DataTable ──────────────────────────────────────────────────────────────

export function DataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: string[][];
}) {
  return (
    <div
      style={{
        margin: "20px 0",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--glass-border)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
        }}
      >
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                style={{
                  padding: "10px 14px",
                  textAlign: "left",
                  fontWeight: 700,
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  color: "var(--text-tertiary)",
                  borderBottom: "1px solid var(--glass-border)",
                  background: "rgba(255,255,255,0.02)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    padding: "8px 14px",
                    color:
                      ci === 0 ? "var(--secondary)" : "var(--text-secondary)",
                    fontFamily: ci === 0 ? "'Fira Code', monospace" : "inherit",
                    fontWeight: ci === 0 ? 600 : 400,
                    borderBottom:
                      ri < rows.length - 1
                        ? "1px solid rgba(255,255,255,0.04)"
                        : "none",
                    lineHeight: 1.5,
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Strip orphaned bold/italic markers at edges of text fragments. */
function cleanOrphanedMarkdown(text: string): string {
  // Remove leading/trailing ** or * that are unpaired (orphaned by entity marker splitting)
  let s = text;
  s = s.replace(/^\s*\*{1,2}\s*(?=\S|$)/g, (m) => m.replace(/\*/g, ""));
  s = s.replace(/(?:^|\S)\s*\*{1,2}\s*$/g, (m) => m.replace(/\*/g, ""));
  return s;
}

// ─── ProseRenderer ──────────────────────────────────────────────────────────

export function ProseRenderer({
  segments,
  base,
}: {
  segments: ProseSegment[];
  base: string;
}) {
  if (!segments || segments.length === 0) return null;

  // Strategy: Re-assemble segments into a single Markdown string with placeholders
  // for non-text components, then render once to preserve list/block context.

  const chipMap = new Map<string, React.ReactNode>();
  const diagramMap = new Map<string, React.ReactNode>();
  const codeBlockMap = new Map<string, React.ReactNode>();

  let fullMarkdown = "";

  // Conservative pre-processing: strip backticks only when clearly at the segment boundary
  // (segment starts/ends with backtick adjacent to a source_link chip).
  // Complex mid-segment cases (e.g. `data.pop(chip, None)`) are handled by the code renderer.
  const cleanedSegments = segments.map((seg, i) => {
    if (seg.type !== "text") return seg;
    let content = seg.content || "";
    const prevIsSL = segments[i - 1]?.type === "source_link";
    const nextIsSL = segments[i + 1]?.type === "source_link";

    // After a chip: strip leading backtick if it closes the chip's code span
    if (prevIsSL && content.trimStart().startsWith("`")) {
      const firstBt = content.indexOf("`");
      content = content.slice(0, firstBt) + content.slice(firstBt + 1);
    }
    // Before a chip: strip trailing backtick if it opens the chip's code span
    if (nextIsSL && content.trimEnd().endsWith("`")) {
      const lastBt = content.lastIndexOf("`");
      content = content.slice(0, lastBt) + content.slice(lastBt + 1);
    }

    return { ...seg, content };
  });

  cleanedSegments.forEach((seg, i) => {
    // Unique IDs that are very unlikely to be part of normal text
    const id = `COMPIDV2X${i}`;

    switch (seg.type) {
      case "text":
        fullMarkdown += seg.content || "";
        break;
      case "source_link":
        // INLINE: Use markdown link. Caught by 'a' renderer. Avoids backtick conflicts with surrounding text.
        fullMarkdown += `[chip](${id})`;
        chipMap.set(
          id,
          <SourceLinkChip key={i} name={seg.name || ""} url={seg.url} />,
        );
        break;
      case "section_link":
        // INLINE: Standard markdown link. Valid inside <p>.
        fullMarkdown += ` [${seg.title || seg.slug}](${id}) `;
        chipMap.set(id, null);
        break;
      case "heading": {
        const level = seg.level || 2;
        const hashes = "#".repeat(level);
        fullMarkdown += `\n\n${hashes} ${seg.text}\n\n`;
        break;
      }
      case "code_block":
        // BLOCK: Use raw ID on its own line. Caught by 'p' renderer.
        fullMarkdown += `\n\n${id}\n\n`;
        codeBlockMap.set(
          id,
          <EmbeddedCodeBlock
            key={i}
            language={seg.language || "text"}
            code={seg.code || ""}
            filePath={seg.file_path}
            startLine={seg.start_line}
          />,
        );
        break;
      case "diagram":
        // BLOCK: Use raw ID on its own line. Caught by 'p' renderer.
        fullMarkdown += `\n\n${id}\n\n`;
        diagramMap.set(
          id,
          <MermaidDiagram
            key={i}
            source={seg.mermaid_source || ""}
            caption={seg.caption}
          />,
        );
        break;
      case "table":
        // BLOCK: Use raw ID on its own line. Caught by 'p' renderer.
        fullMarkdown += `\n\n${id}\n\n`;
        diagramMap.set(
          id,
          <DataTable
            key={i}
            headers={seg.headers || []}
            rows={seg.rows || []}
          />,
        );
        break;
    }
  });

  return (
    <div className="v2-prose" style={{ lineHeight: 1.8 }}>
      <ReactMarkdown
        components={{
          p: ({ children }) => {
            // Aggressively stringify children to find block markers
            const content = React.Children.toArray(children)
              .map((child) => (typeof child === "string" ? child : ""))
              .join("")
              .trim();

            // If the entire paragraph is just a block ID, return the component directly (NOT wrapped in <p>)
            if (codeBlockMap.has(content))
              return <div key={content}>{codeBlockMap.get(content)}</div>;
            if (diagramMap.has(content))
              return <div key={content}>{diagramMap.get(content)}</div>;

            return (
              <p
                style={{
                  marginBottom: 16,
                  color: "var(--text-secondary)",
                  lineHeight: 1.7,
                }}
              >
                {children}
              </p>
            );
          },
          code: ({ children, className, inline, ...props }: any) => {
            const content = React.Children.toArray(children).join("").trim();

            // Handle inline chip placeholders (direct match)
            if (chipMap.has(content)) return <>{chipMap.get(content)}</>;

            // Fallback: chip embedded inside a code span (e.g. `data.pop([chip](COMPIDV2X74), None)`)
            // This happens when segment splitting puts a chip reference inside a backtick code span.
            // Extract the chip(s) and render them, stripping the surrounding code text.
            if (/\[chip\]\(COMPIDV2X\d+\)/.test(content)) {
              const chips: React.ReactNode[] = [];
              content.replace(
                /\[chip\]\(COMPIDV2X(\d+)\)/g,
                (_match: string, idx: string) => {
                  const chip = chipMap.get(`COMPIDV2X${idx}`);
                  if (chip) chips.push(chip);
                  return "";
                },
              );
              return chips.length > 0 ? <>{chips}</> : null;
            }

            return (
              <code
                style={{
                  padding: "2px 6px",
                  background: "rgba(255,255,255,0.08)",
                  borderRadius: 4,
                  fontSize: "0.9em",
                  fontFamily: "'Fira Code', monospace",
                  color: "var(--secondary)",
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          // Standard elements
          h1: ({ children }) => (
            <h1
              style={{
                color: "var(--text-primary)",
                fontSize: 32,
                fontWeight: 800,
                margin: "32px 0 16px",
              }}
            >
              {children}
            </h1>
          ),
          h2: ({ children }) => {
            const text = React.Children.toArray(children).join("");
            const anchorId = text
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, "-")
              .replace(/^-|-$/g, "");
            return (
              <h2
                id={anchorId}
                style={{
                  color: "var(--text-primary)",
                  fontSize: 24,
                  fontWeight: 700,
                  margin: "36px 0 16px",
                }}
              >
                {children}
              </h2>
            );
          },
          h3: ({ children }) => {
            const text = React.Children.toArray(children).join("");
            const anchorId = text
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, "-")
              .replace(/^-|-$/g, "");
            return (
              <h3
                id={anchorId}
                style={{
                  color: "var(--text-primary)",
                  fontSize: 20,
                  fontWeight: 700,
                  margin: "28px 0 12px",
                }}
              >
                {children}
              </h3>
            );
          },
          ul: ({ children }) => (
            <ul
              style={{
                margin: "12px 0 16px",
                paddingLeft: 24,
                listStyleType: "disc",
                color: "var(--text-secondary)",
              }}
            >
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol
              style={{
                margin: "12px 0 16px",
                paddingLeft: 24,
                listStyleType: "decimal",
                color: "var(--text-secondary)",
              }}
            >
              {children}
            </ol>
          ),
          li: ({ children }) => <li style={{ marginBottom: 8 }}>{children}</li>,
          a: ({ href, children }) => {
            if (href && href.startsWith("COMPIDV2X")) {
              const segIdx = parseInt(href.replace(/COMPIDV2X(\d+)/, "$1"));
              const seg = segments[segIdx];
              if (seg) {
                // Block components: return the pre-built React node
                if (seg.type === "code_block")
                  return <>{codeBlockMap.get(href)}</>;
                if (seg.type === "diagram" || seg.type === "table")
                  return <>{diagramMap.get(href)}</>;
                // Source link chips
                if (seg.type === "source_link") return <>{chipMap.get(href)}</>;
                // Section links
                if (seg.type === "section_link" && seg.slug) {
                  return (
                    <Link
                      href={`${base}/${seg.slug}`}
                      style={{
                        color: "var(--primary-light)",
                        textDecoration: "underline",
                        textDecorationColor: "rgba(139,92,246,0.3)",
                        textUnderlineOffset: 3,
                      }}
                    >
                      {children}
                    </Link>
                  );
                }
              }
              return null;
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "var(--primary-light)",
                  textDecoration: "underline",
                  textDecorationColor: "rgba(139,92,246,0.3)",
                  textUnderlineOffset: 3,
                }}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {fullMarkdown}
      </ReactMarkdown>
    </div>
  );
}

// ─── V2SectionContent ───────────────────────────────────────────────────────

export function V2SectionContent({
  content,
  base,
  name,
}: {
  content: Record<string, unknown>;
  base: string;
  name: string;
}) {
  const segments = (content.prose_segments as ProseSegment[]) || [];
  const tables = (content.tables as TableData[]) || [];
  const location = content.location as {
    files?: string[];
    file_count?: number;
  } | null;
  const commitHash = content.commit_hash as string | null;

  return (
    <>
      {/* Meta bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          color: "var(--text-tertiary)",
          marginBottom: 24,
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--success)",
            display: "inline-block",
            boxShadow: "0 0 6px var(--success)",
          }}
        />
        {commitHash && (
          <>
            <span>Commit:</span>
            <span
              style={{
                fontFamily: "'Fira Code', monospace",
                color: "var(--primary-light)",
              }}
            >
              {commitHash.slice(0, 7)}
            </span>
            <span>·</span>
          </>
        )}
        <span>V2 Auto-generated</span>
        {location?.file_count != null && (
          <>
            <span>·</span>
            <span>{location.file_count} files</span>
          </>
        )}
      </div>

      {/* Main prose content (includes interleaved diagrams) */}
      <ProseRenderer segments={segments} base={base} />

      {/* Tables */}
      {tables.map((t, i) => (
        <DataTable key={i} headers={t.headers} rows={t.rows} />
      ))}
    </>
  );
}

// ─── V2HomeContent ──────────────────────────────────────────────────────────

export function V2HomeContent({
  content,
  base,
  name,
}: {
  content: Record<string, unknown>;
  base: string;
  name: string;
}) {
  const sectionSummaries =
    (content.section_summaries as SectionSummary[]) || [];
  const stats = content.stats as Record<string, number> | null;
  const segments = (content.prose_segments as ProseSegment[]) || [];
  const overview_diagram =
    (content.overview_diagram as {
      mermaid_source: string;
      caption: string;
    } | null) ?? null;
  const overview = content.overview as Record<string, unknown> | null;
  const systemContext = (() => {
    const raw = (content.system_context as string | null) ||
      (overview?.project_description as string | null) || null;
    if (!raw) return null;
    // Strip heading markers like [[heading:2:text]] and trim
    return raw.replace(/\[\[heading:\d+:([^\]]*)\]\]/g, '$1').replace(/\s+/g, ' ').trim().slice(0, 500);
  })();

  return (
    <>
      <h1
        id="overview"
        style={{
          fontSize: 32,
          fontWeight: 800,
          marginTop: 24,
          marginBottom: 16,
          letterSpacing: "-0.02em",
          color: "var(--text-primary)",
        }}
      >
        {name}
      </h1>

      {/* ── C4 Level 1: System Context ── */}
      {systemContext && (
        <div style={{
          background: "linear-gradient(135deg, rgba(139,92,246,0.08), rgba(6,182,212,0.05))",
          border: "1px solid rgba(139,92,246,0.2)",
          borderRadius: 16,
          padding: "20px 24px",
          marginBottom: 32,
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--primary-light)", marginBottom: 8 }}>What is this?</div>
          <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)", margin: 0 }}>{systemContext}</p>
        </div>
      )}

      {/* ── C4 Level 2: Architecture Overview ── */}
      {overview_diagram && (
        <div style={{ margin: "0 0 40px" }}>
          <h2
            id="architecture-overview"
            style={{ fontSize: 22, fontWeight: 700, margin: "0 0 16px" }}
          >
            Architecture Overview
          </h2>
          <MermaidDiagram
            source={overview_diagram.mermaid_source}
            caption={overview_diagram.caption}
          />
        </div>
      )}

      {/* System narrative (Structured with resolved headings) */}
      <div style={{ marginBottom: 48 }}>
        <ProseRenderer segments={segments} base={base} />
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ marginTop: 24 }}>
          <h2
            id="stats"
            style={{ fontSize: 22, fontWeight: 700, margin: "36px 0 16px" }}
          >
            Repository Stats
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: 12,
              marginBottom: 36,
            }}
          >
            {[
              {
                value: stats.modules ?? stats.sections ?? 0,
                label: "Sections",
              },
              { value: stats.files ?? 0, label: "Files" },
              {
                value: stats.loc
                  ? stats.loc > 1000
                    ? `${(stats.loc / 1000).toFixed(1)}k`
                    : stats.loc
                  : "—",
                label: "Lines of Code",
              },
              {
                value: stats.total_words
                  ? stats.total_words > 1000
                    ? `${(stats.total_words / 1000).toFixed(1)}k`
                    : stats.total_words
                  : "—",
                label: "Words",
              },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  padding: "20px 16px",
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid var(--glass-border)",
                  borderRadius: 14,
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    fontSize: 28,
                    fontWeight: 800,
                    background:
                      "linear-gradient(135deg, var(--primary-light), var(--secondary))",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                    marginBottom: 4,
                  }}
                >
                  {s.value}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-tertiary)",
                    fontWeight: 500,
                  }}
                >
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section summary cards */}
      {sectionSummaries.length > 0 && (
        <>
          <h2
            id="sections"
            style={{ fontSize: 22, fontWeight: 700, margin: "36px 0 16px" }}
          >
            System Modules
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 14,
              marginBottom: 48,
            }}
          >
            {sectionSummaries.map((s) => (
              <Link
                key={s.id}
                href={`${base}/${s.id}`}
                style={{
                  display: "block",
                  padding: 20,
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid var(--glass-border)",
                  borderRadius: 14,
                  textDecoration: "none",
                  transition: "all 0.2s",
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.borderColor = "rgba(139,92,246,0.3)";
                  e.currentTarget.style.transform = "translateY(-2px)";
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.borderColor = "var(--glass-border)";
                  e.currentTarget.style.transform = "none";
                }}
              >
                <h3
                  style={{
                    fontSize: 15,
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    marginBottom: 8,
                  }}
                >
                  {s.title}
                </h3>
                <div
                  style={{
                    display: "flex",
                    gap: 12,
                    fontSize: 12,
                    color: "var(--text-tertiary)",
                  }}
                >
                  <span>
                    <strong style={{ color: "var(--text-primary)" }}>
                      {s.word_count}
                    </strong>{" "}
                    words
                  </span>
                  {s.diagram_count > 0 && (
                    <span>
                      <strong style={{ color: "var(--text-primary)" }}>
                        {s.diagram_count}
                      </strong>{" "}
                      diagram{s.diagram_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// ─── GettingStartedContent ───────────────────────────────────────────────────

type SetupStep = { step: number; title: string; command?: string | null; description?: string };
type Prerequisite = { name: string; version?: string; description?: string };
type ConfigItem = { key: string; description?: string; required?: boolean };

export function GettingStartedContent({
  content,
}: {
  content: Record<string, unknown>;
}) {
  const prerequisites = (content.prerequisites as Prerequisite[]) || [];
  const steps = (content.setup_steps as SetupStep[]) || [];
  const config = (content.configuration as ConfigItem[]) || [];

  const sectionStyle = { marginBottom: 40 };
  const h2Style: React.CSSProperties = {
    fontSize: 22,
    fontWeight: 700,
    marginBottom: 16,
    color: "var(--text-primary)",
  };
  const cardStyle: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid var(--glass-border)",
    borderRadius: 12,
    padding: "16px 20px",
    marginBottom: 10,
  };

  return (
    <>
      {prerequisites.length > 0 && (
        <div style={sectionStyle}>
          <h2 id="prerequisites" style={h2Style}>Prerequisites</h2>
          {prerequisites.map((p, i) => (
            <div key={i} style={cardStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: p.description ? 6 : 0 }}>
                <span style={{ fontFamily: "'Fira Code', monospace", fontWeight: 700, color: "var(--primary-light)" }}>{p.name}</span>
                {p.version && p.version !== "any" && (
                  <span style={{ fontSize: 12, color: "var(--text-tertiary)", background: "rgba(255,255,255,0.07)", padding: "2px 8px", borderRadius: 6 }}>{p.version}</span>
                )}
              </div>
              {p.description && <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0 }}>{p.description}</p>}
            </div>
          ))}
        </div>
      )}

      {steps.length > 0 && (
        <div style={sectionStyle}>
          <h2 id="setup" style={h2Style}>Setup Steps</h2>
          {steps.map((s, i) => (
            <div key={i} style={{ ...cardStyle, display: "flex", gap: 16, alignItems: "flex-start" }}>
              <div style={{
                minWidth: 32, height: 32, borderRadius: "50%",
                background: "linear-gradient(135deg, var(--primary), var(--secondary))",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 800, color: "#fff", flexShrink: 0,
              }}>{s.step}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, marginBottom: s.command || s.description ? 8 : 0, color: "var(--text-primary)" }}>{s.title}</div>
                {s.command && (
                  <pre style={{
                    fontFamily: "'Fira Code', monospace", fontSize: 13,
                    background: "rgba(0,0,0,0.4)", border: "1px solid var(--glass-border)",
                    borderRadius: 8, padding: "10px 14px", margin: "0 0 8px",
                    color: "var(--success)", overflowX: "auto",
                  }}>{s.command}</pre>
                )}
                {s.description && <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0 }}>{s.description}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {config.length > 0 && (
        <div style={sectionStyle}>
          <h2 id="configuration" style={h2Style}>Configuration</h2>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--glass-border)" }}>
                  {["Variable", "Required", "Description"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 12px", color: "var(--text-tertiary)", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {config.map((c, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "'Fira Code', monospace", color: "var(--primary-light)" }}>{c.key}</td>
                    <td style={{ padding: "10px 12px", color: c.required ? "var(--danger)" : "var(--text-tertiary)" }}>{c.required ? "Yes" : "No"}</td>
                    <td style={{ padding: "10px 12px", color: "var(--text-secondary)" }}>{c.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {steps.length === 0 && prerequisites.length === 0 && config.length === 0 && (
        <p style={{ color: "var(--text-tertiary)" }}>Getting started information will be available after the wiki is regenerated.</p>
      )}
    </>
  );
}

// ─── GlossaryContent ─────────────────────────────────────────────────────────

type GlossaryTerm = { term: string; type?: string; definition?: string; related_terms?: string[] };

export function GlossaryContent({ content }: { content: Record<string, unknown> }) {
  const terms = (content.terms as GlossaryTerm[]) || [];
  const [filter, setFilter] = useState("");

  const filtered = filter
    ? terms.filter((t) => t.term.toLowerCase().includes(filter.toLowerCase()))
    : terms;

  // Group by first letter
  const grouped: Record<string, GlossaryTerm[]> = {};
  for (const t of filtered) {
    const letter = (t.term[0] || "#").toUpperCase();
    grouped[letter] = grouped[letter] || [];
    grouped[letter].push(t);
  }

  const typeColors: Record<string, string> = {
    concept: "rgba(139,92,246,0.3)",
    pattern: "rgba(6,182,212,0.3)",
    acronym: "rgba(245,158,11,0.3)",
    entity: "rgba(52,211,153,0.3)",
  };

  if (terms.length === 0) {
    return <p style={{ color: "var(--text-tertiary)" }}>The glossary will be populated after the wiki is regenerated with enriched content.</p>;
  }

  return (
    <>
      <div style={{ marginBottom: 24 }}>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter terms…"
          style={{
            width: "100%", maxWidth: 360,
            background: "rgba(255,255,255,0.05)", border: "1px solid var(--glass-border)",
            borderRadius: 10, padding: "8px 14px", color: "var(--text-primary)",
            fontFamily: "'Outfit', sans-serif", fontSize: 14, outline: "none",
          }}
        />
      </div>
      {Object.keys(grouped).sort().map((letter) => (
        <div key={letter} style={{ marginBottom: 32 }}>
          <h2 id={`letter-${letter}`} style={{ fontSize: 20, fontWeight: 800, color: "var(--primary-light)", marginBottom: 12 }}>{letter}</h2>
          {grouped[letter].map((t, i) => (
            <div key={i} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: "14px 18px", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>{t.term}</span>
                {t.type && (
                  <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 6, background: typeColors[t.type] || "rgba(255,255,255,0.08)", color: "var(--text-secondary)", fontWeight: 600 }}>{t.type}</span>
                )}
              </div>
              {t.definition && <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: "0 0 8px" }}>{t.definition}</p>}
              {t.related_terms && t.related_terms.length > 0 && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  Related: {t.related_terms.join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

// ─── ApiReferenceContent / FunctionIndexContent ───────────────────────────────

type IndexEntry = {
  name: string;
  qualified_name: string;
  type: string;
  file: string;
  line?: number;
  signature?: string;
  description?: string;
  summary?: string;
};

function EntityIndexContent({
  index,
  totalCount,
  repoUrl,
  commitHash,
}: {
  index: Record<string, IndexEntry[]>;
  totalCount: number;
  repoUrl?: string;
  commitHash?: string;
}) {
  const [filter, setFilter] = useState("");

  const typeColor: Record<string, string> = {
    function: "rgba(6,182,212,0.2)",
    class: "rgba(139,92,246,0.2)",
    method: "rgba(52,211,153,0.2)",
  };

  const buildUrl = (entry: IndexEntry) => {
    if (!repoUrl) return null;
    const base = repoUrl.replace(/\.git$/, "");
    const ref = commitHash ? `/blob/${commitHash}` : "/blob/HEAD";
    return `${base}${ref}/${entry.file}${entry.line ? `#L${entry.line}` : ""}`;
  };

  const filteredIndex: Record<string, IndexEntry[]> = {};
  for (const [letter, entries] of Object.entries(index)) {
    const filtered = filter
      ? entries.filter((e) => e.name.toLowerCase().includes(filter.toLowerCase()) || e.qualified_name.toLowerCase().includes(filter.toLowerCase()))
      : entries;
    if (filtered.length > 0) filteredIndex[letter] = filtered;
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by name…"
          style={{
            flex: 1, maxWidth: 400,
            background: "rgba(255,255,255,0.05)", border: "1px solid var(--glass-border)",
            borderRadius: 10, padding: "8px 14px", color: "var(--text-primary)",
            fontFamily: "'Outfit', sans-serif", fontSize: 14, outline: "none",
          }}
        />
        <span style={{ fontSize: 13, color: "var(--text-tertiary)" }}>{totalCount} entries</span>
      </div>

      {Object.keys(filteredIndex).sort().map((letter) => (
        <div key={letter} style={{ marginBottom: 28 }}>
          <h2 id={`letter-${letter}`} style={{ fontSize: 18, fontWeight: 800, color: "var(--primary-light)", marginBottom: 10, borderBottom: "1px solid var(--glass-border)", paddingBottom: 6 }}>{letter}</h2>
          {filteredIndex[letter].map((e, i) => {
            const url = buildUrl(e);
            return (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                <span style={{ minWidth: 64, fontSize: 11, padding: "2px 8px", borderRadius: 6, background: typeColor[e.type] || "rgba(255,255,255,0.07)", color: "var(--text-secondary)", fontWeight: 600, flexShrink: 0, marginTop: 2 }}>{e.type}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontFamily: "'Fira Code', monospace", fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>{e.name}</span>
                    {url && (
                      <a href={url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--text-tertiary)", textDecoration: "none" }}>
                        {e.file}{e.line ? `:${e.line}` : ""}
                      </a>
                    )}
                    {!url && (
                      <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{e.file}{e.line ? `:${e.line}` : ""}</span>
                    )}
                  </div>
                  {e.signature && <div style={{ fontFamily: "'Fira Code', monospace", fontSize: 12, color: "var(--text-tertiary)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.signature}</div>}
                  {(e.description || e.summary) && <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>{e.description || e.summary}</div>}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}

export function ApiReferenceContent({
  content,
  repoUrl,
}: {
  content: Record<string, unknown>;
  repoUrl?: string;
}) {
  const index = (content.index as Record<string, IndexEntry[]>) || {};
  const totalCount = (content.total_count as number) || 0;
  const commitHash = content.commit_hash as string | undefined;
  return <EntityIndexContent index={index} totalCount={totalCount} repoUrl={repoUrl} commitHash={commitHash} />;
}

export function FunctionIndexContent({
  content,
  repoUrl,
}: {
  content: Record<string, unknown>;
  repoUrl?: string;
}) {
  const index = (content.index as Record<string, IndexEntry[]>) || {};
  const totalCount = (content.total_count as number) || 0;
  const commitHash = content.commit_hash as string | undefined;
  return <EntityIndexContent index={index} totalCount={totalCount} repoUrl={repoUrl} commitHash={commitHash} />;
}

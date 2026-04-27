"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { motion } from "motion/react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SourceFragment, SourceGroup } from "@/lib/types";
import { SourcesAccordion } from "@/components/chat/SourcesAccordion";

interface AssistantBubbleProps {
  text: string;
  sources: SourceGroup[];
}

interface PopoverState {
  fragmentIndex: number;
  top: number;
  left: number;
}

// Etiquetas a mostrar en el popover (orden de aparición + texto del label).
const POPOVER_DOC_META: Array<[string, string]> = [
  ["Corporación", "Corporación"],
  ["Radicado", "Radicado"],
  ["Magistrado ponente", "Magistrado"],
  ["Tema principal", "Tema"],
];

function metaString(meta: Record<string, unknown>, key: string): string {
  const v = meta[key];
  return typeof v === "string" ? v : "";
}

/**
 * Prepares the raw LLM text for ReactMarkdown:
 * 1. Normalizes line endings.
 * 2. Ensures blank lines before list markers so remark parses them as <ul>/<ol>.
 * 3. Ensures blank lines after standalone **Title** lines (lines whose entire
 *    content is bold text) so the title and the following paragraph are separate
 *    <p> elements instead of being merged into one.
 * 4. Converts [docN] citation markers into markdown links with a special href
 *    (#docref-N) that the `components.a` handler intercepts.
 */
function prepareMarkdown(raw: string): string {
  let text = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  // Blank line before list markers immediately following non-blank content.
  text = text.replace(/([^\n])\n([ \t]*[-*+] |[ \t]*\d+\. )/g, "$1\n\n$2");
  // Blank line after a line whose entire content is **bold** (section titles).
  // Pattern: line is exactly **...** (optionally with trailing spaces/asterisks
  // as in **Title** *(optional note)*), followed immediately by a non-blank line.
  text = text.replace(/^(\*\*[^*\n]+\*\*[^\n]*)\n([^\n])/gm, "$1\n\n$2");
  // [docN] → markdown link intercepted by components.a
  text = text.replace(/\[doc(\d+)\]/g, (match, n) => `[${match}](#docref-${n})`);
  return text;
}

export function AssistantBubble({ text, sources }: AssistantBubbleProps) {
  const processedText = useMemo(() => prepareMarkdown(text), [text]);

  // Mapa global: índice de fragmento ([docN] → N) → fragmento + grupo padre.
  const fragmentLookup = useMemo(() => {
    const map = new Map<number, { group: SourceGroup; fragment: SourceFragment }>();
    for (const group of sources) {
      for (const fragment of group.fragments) {
        map.set(fragment.index, { group, fragment });
      }
    }
    return map;
  }, [sources]);

  const [popover, setPopoverState] = useState<PopoverState | null>(null);

  // Ref-synced copy of popover state so the `components` memo closure can
  // read the current value without needing popover in its dependency array
  // (which would cause ReactMarkdown to unmount/remount on every open/close).
  const popoverRef = useRef<PopoverState | null>(null);
  const popoverElRef = useRef<HTMLDivElement>(null);
  const proseRef = useRef<HTMLDivElement>(null);

  const setPopover = useCallback((p: PopoverState | null) => {
    popoverRef.current = p;
    setPopoverState(p);
  }, []);

  // Close on outside click or Escape while popover is open.
  useEffect(() => {
    if (!popover) return;

    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Element;
      if (popoverElRef.current?.contains(target)) return;
      if (target.closest("[data-doc-badge]")) return;
      setPopover(null);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPopover(null);
    };

    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [popover, setPopover]);

  // ReactMarkdown component overrides. Defined with useMemo so that the
  // markdown tree is not rebuilt on every render — only when setPopover or
  // proseRef identity changes (i.e. effectively once).
  const components = useMemo<Components>(
    () => ({
      // Intercept links whose href matches the #docref-N pattern we injected.
      a({ href, children }) {
        const match = href?.match(/^#docref-(\d+)$/);
        if (!match) return <a href={href}>{children}</a>;

        const n = parseInt(match[1], 10);
        const hasFragment = fragmentLookup.has(n);

        return (
          <button
            type="button"
            className={`doc-badge${hasFragment ? "" : " doc-badge--missing"}`}
            data-doc-badge={n}
            aria-label={hasFragment ? `Ver fuente ${n}` : `Fuente ${n} no disponible`}
            aria-disabled={!hasFragment}
            onClick={(e) => {
              e.preventDefault();

              // Toggle: close if same badge was clicked again.
              if (popoverRef.current?.fragmentIndex === n) {
                setPopover(null);
                return;
              }

              if (!hasFragment) return;
              if (!proseRef.current) return;

              const btn = e.currentTarget;
              const wrapperRect = proseRef.current.getBoundingClientRect();
              const btnRect = btn.getBoundingClientRect();

              setPopover({
                fragmentIndex: n,
                top: btnRect.bottom - wrapperRect.top + 6,
                left: Math.max(
                  0,
                  Math.min(
                    btnRect.left - wrapperRect.left,
                    wrapperRect.width - 360
                  )
                ),
              });
            }}
          >
            {n}
          </button>
        );
      },
    }),
    [setPopover, fragmentLookup]
  );

  const active = popover ? fragmentLookup.get(popover.fragmentIndex) ?? null : null;

  // Metadatos del documento que existen y son no vacíos.
  const docMeta = useMemo(() => {
    if (!active) return [];
    return POPOVER_DOC_META.map(([key, label]) => {
      const value = metaString(active.group.metadata, key);
      return value ? { label, value } : null;
    }).filter((x): x is { label: string; value: string } => x !== null);
  }, [active]);

  return (
    <motion.div
      className="flex justify-start"
      initial={{ opacity: 0, y: 10, x: -8 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <div
        className="max-w-[88%] min-w-0 break-words rounded-2xl rounded-tl-sm bg-surface px-5 py-4 text-sm leading-relaxed text-foreground shadow-sm"
        style={{
          border: "1px solid var(--border)",
          borderLeftColor: "var(--navy)",
          borderLeftWidth: "3px",
        }}
      >
        <div className="rag-prose relative" ref={proseRef}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {processedText}
          </ReactMarkdown>

          {popover && active && (
            <div
              ref={popoverElRef}
              className="doc-popover doc-popover--rich"
              role="tooltip"
              style={{ top: popover.top, left: popover.left }}
            >
              {active.group.title && (
                <p className="doc-popover-title" translate="no">
                  {active.group.title}
                </p>
              )}

              {docMeta.length > 0 && (
                <dl className="doc-popover-meta">
                  {docMeta.map(({ label, value }) => (
                    <div key={label} className="doc-popover-meta-row">
                      <dt>{label}</dt>
                      <dd translate="no">{value}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {(() => {
                const section =
                  metaString(active.fragment.metadata, "section_name") ||
                  metaString(active.fragment.metadata, "section_heading");
                return section ? (
                  <p className="doc-popover-section" translate="no">
                    {section}
                  </p>
                ) : null;
              })()}

              {(() => {
                const summary = metaString(active.fragment.metadata, "summary");
                return summary ? (
                  <p className="doc-popover-summary">{summary}</p>
                ) : null;
              })()}

              <p className="doc-popover-content doc-popover-content--scroll">
                {active.fragment.content}
              </p>

              {active.group.source && (
                <p className="doc-popover-source" translate="no">
                  {active.group.source}
                </p>
              )}
            </div>
          )}
        </div>
        <SourcesAccordion sources={sources} />
      </div>
    </motion.div>
  );
}

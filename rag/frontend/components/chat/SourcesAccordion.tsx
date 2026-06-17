"use client";

import { useId, useState } from "react";
import type { DocType, SourceGroup, SourceMetadata } from "@/lib/types";

interface SourcesAccordionProps {
  sources: SourceGroup[];
}

// Atribución para jurisprudencia (orden de aparición + clave de metadata).
const JURIS_META_LABELS: Array<[string, string]> = [
  ["Corporación", "Corporación"],
  ["Radicado", "Radicado"],
  ["Magistrado ponente", "Magistrado ponente"],
  ["Tema principal", "Tema"],
];

// Atribución para normativa. La norma se muestra como título del grupo, así que
// aquí solo van Título / Capítulo / Artículo.
const NORMA_META_LABELS: Array<[string, string]> = [
  ["titulo", "Título"],
  ["capitulo", "Capítulo"],
  ["articulo", "Artículo"],
];

function metaString(meta: Record<string, unknown>, key: string): string {
  const v = meta[key];
  return typeof v === "string" ? v : "";
}

/** Deriva el tipo de fuente; ausencia de `doc_type` ⇒ jurisprudencia. */
function docTypeOf(meta: SourceMetadata): DocType {
  return meta.doc_type === "normativa" ? "normativa" : "jurisprudencia";
}

/** Atributos visuales del badge por tipo de fuente. */
const TYPE_BADGE: Record<DocType, { label: string; className: string }> = {
  jurisprudencia: {
    label: "Jurisprudencia",
    className: "bg-accent-soft text-accent",
  },
  normativa: {
    label: "Normativa",
    className:
      "border border-border-strong/60 bg-elevated text-muted",
  },
};

export function SourcesAccordion({ sources }: SourcesAccordionProps) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  if (sources.length === 0) return null;

  const docCount = sources.length;
  const fragmentCount = sources.reduce((acc, g) => acc + g.fragments.length, 0);
  const headerText =
    fragmentCount === docCount
      ? `${docCount} ${docCount === 1 ? "fuente consultada" : "fuentes consultadas"}`
      : `${docCount} ${docCount === 1 ? "fuente" : "fuentes"} (${fragmentCount} fragmentos)`;

  return (
    <div className="mt-5 border-t border-border pt-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-full text-xs text-muted transition-colors duration-150 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className="flex items-center gap-1.5 font-medium">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          {headerText}
        </span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="shrink-0 transition-transform duration-300 ease-in-out"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transformBox: "fill-box",
            transformOrigin: "center",
          }}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {/* CSS grid trick — animates height without JS measurement */}
      <div
        id={contentId}
        aria-hidden={!open}
        className="grid overflow-hidden"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          transitionProperty: "grid-template-rows",
          transitionDuration: "300ms",
          transitionTimingFunction: "cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <div className="overflow-hidden">
          <ul className="mt-3 divide-y divide-border" role="list">
            {sources.map((group, gi) => {
              const docType = docTypeOf(group.metadata);
              const isNorma = docType === "normativa";
              const badge = TYPE_BADGE[docType];

              // Título del grupo: para normativa preferimos `norma` si existe.
              const groupTitle = isNorma
                ? metaString(group.metadata, "norma") || group.title
                : group.title;

              const metaLabels = isNorma ? NORMA_META_LABELS : JURIS_META_LABELS;
              const docMeta = metaLabels
                .map(([key, label]) => {
                  const value = metaString(group.metadata, key);
                  return value ? { label, value } : null;
                })
                .filter((x): x is { label: string; value: string } => x !== null);

              return (
                <li
                  key={`${group.source}-${gi}`}
                  className={gi === 0 ? "pb-3" : "py-3"}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ${badge.className}`}
                    >
                      {badge.label}
                    </span>
                    {groupTitle && (
                      <p
                        className="truncate text-sm font-semibold text-foreground"
                        translate="no"
                      >
                        {groupTitle}
                      </p>
                    )}
                  </div>

                  {docMeta.length > 0 && (
                    <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px] text-muted">
                      {docMeta.map(({ label, value }) => (
                        <div key={label} className="contents">
                          <dt className="font-medium text-muted/70">{label}:</dt>
                          <dd className="truncate" translate="no">
                            {value}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  <ul className="mt-2.5 flex flex-col gap-2" role="list">
                    {group.fragments.map((frag) => {
                      const section =
                        metaString(frag.metadata, "section_name") ||
                        metaString(frag.metadata, "section_heading");
                      return (
                        <li
                          key={frag.index}
                          className="flex gap-2.5"
                        >
                          <span className="mt-0.5 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft px-1.5 text-[10px] font-semibold text-accent">
                            {frag.index}
                          </span>
                          <div className="min-w-0 border-l border-border pl-3">
                            {section && (
                              <span
                                className="mb-0.5 block truncate text-[10px] text-muted/80"
                                translate="no"
                              >
                                {section}
                              </span>
                            )}
                            <p className="line-clamp-3 text-xs leading-relaxed text-muted">
                              {frag.content}
                            </p>
                          </div>
                        </li>
                      );
                    })}
                  </ul>

                  {group.source && (
                    <p
                      className="mt-3 truncate font-(family-name:--font-mono,monospace) text-[10px] text-muted/60"
                      translate="no"
                    >
                      {group.source}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

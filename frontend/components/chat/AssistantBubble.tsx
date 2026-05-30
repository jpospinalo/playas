"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { motion } from "motion/react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
	DocType,
	SourceFragment,
	SourceGroup,
	SourceMetadata,
} from "@/lib/types";
import { SourcesAccordion } from "@/components/chat/SourcesAccordion";
import { MessageRatingPopover } from "@/components/chat/MessageRatingPopover";

interface AssistantBubbleProps {
	text: string;
	sources: SourceGroup[];
	messageId: string;
	conversationId: string;
	isRated: boolean;
	onRate: (
		messageId: string,
		ratings: { pertinence: number; accuracy: number },
		expectedAnswer?: string,
	) => Promise<void>;
}

interface PopoverState {
	fragmentIndex: number;
	top: number;
	left: number;
}

// Etiquetas del popover para jurisprudencia (orden + clave/label).
const POPOVER_JURIS_META: Array<[string, string]> = [
	["Corporación", "Corporación"],
	["Radicado", "Radicado"],
	["Magistrado ponente", "Magistrado"],
	["Tema principal", "Tema"],
];

// Etiquetas del popover para normativa.
const POPOVER_NORMA_META: Array<[string, string]> = [
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

const POPOVER_TYPE_BADGE: Record<DocType, { label: string; className: string }> =
	{
		jurisprudencia: { label: "Jurisprudencia", className: "bg-accent-soft text-accent" },
		normativa: {
			label: "Normativa",
			className: "border border-border-strong/60 bg-elevated text-muted",
		},
	};

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
	text = text.replace(
		/\[doc(\d+)\]/g,
		(match, n) => `[${match}](#docref-${n})`,
	);
	return text;
}

export function AssistantBubble({
	text,
	sources,
	messageId,
	conversationId: _conversationId,
	isRated,
	onRate,
}: AssistantBubbleProps) {
	const processedText = useMemo(() => prepareMarkdown(text), [text]);

	// Mapa global: índice de fragmento ([docN] → N) → fragmento + grupo padre.
	const fragmentLookup = useMemo(() => {
		const map = new Map<
			number,
			{ group: SourceGroup; fragment: SourceFragment }
		>();
		for (const group of sources) {
			for (const fragment of group.fragments) {
				map.set(fragment.index, { group, fragment });
			}
		}
		return map;
	}, [sources]);

	const [popover, setPopoverState] = useState<PopoverState | null>(null);
	const [ratingPopoverOpen, setRatingPopoverOpen] = useState(false);

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
						aria-label={
							hasFragment ? `Ver fuente ${n}` : `Fuente ${n} no disponible`
						}
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
										wrapperRect.width - 360,
									),
								),
							});
						}}
					>
						{n}
					</button>
				);
			},
		}),
		[setPopover, fragmentLookup],
	);

	const active = popover
		? (fragmentLookup.get(popover.fragmentIndex) ?? null)
		: null;

	// Tipo de fuente activa + atribución correspondiente.
	const activeDocType = active ? docTypeOf(active.group.metadata) : null;

	const activeTitle = useMemo(() => {
		if (!active) return "";
		return activeDocType === "normativa"
			? metaString(active.group.metadata, "norma") || active.group.title
			: active.group.title;
	}, [active, activeDocType]);

	// Metadatos del documento que existen y son no vacíos.
	const docMeta = useMemo(() => {
		if (!active) return [];
		const labels =
			activeDocType === "normativa" ? POPOVER_NORMA_META : POPOVER_JURIS_META;
		return labels
			.map(([key, label]) => {
				const value = metaString(active.group.metadata, key);
				return value ? { label, value } : null;
			})
			.filter((x): x is { label: string; value: string } => x !== null);
	}, [active, activeDocType]);

	return (
		<motion.div
			className="group flex w-full justify-start"
			initial={{ opacity: 0, y: 10 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
		>
			<div className="w-full min-w-0">
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
							{activeDocType && (
								<span
									className={`mb-1.5 inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ${POPOVER_TYPE_BADGE[activeDocType].className}`}
								>
									{POPOVER_TYPE_BADGE[activeDocType].label}
								</span>
							)}

							{activeTitle && (
								<p className="doc-popover-title" translate="no">
									{activeTitle}
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

				{/* Action button: rate this message */}
				<div className="relative mt-3 flex justify-end">
					{isRated ? (
						<span
							className="inline-flex items-center gap-1 text-xs text-muted"
							title="Calificación enviada"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="14"
								height="14"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2"
								strokeLinecap="round"
								strokeLinejoin="round"
								className="text-success"
								aria-hidden="true"
							>
								<path d="M20 6 9 17l-5-5" />
							</svg>
							Calificado
						</span>
					) : (
						<button
							type="button"
							onClick={() => setRatingPopoverOpen(true)}
							className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent md:opacity-0 md:group-hover:opacity-100"
							aria-label="Calificar esta respuesta"
							title="Calificar esta respuesta"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="14"
								height="14"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2"
								strokeLinecap="round"
								strokeLinejoin="round"
								aria-hidden="true"
							>
								<path d="M12 20v-6m0 0V4m0 10H4m8 0h16" />
								<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
							</svg>
							Calificar
						</button>
					)}

					{ratingPopoverOpen && !isRated && (
						<MessageRatingPopover
							open={ratingPopoverOpen}
							onSubmit={(ratings, expectedAnswer) =>
								onRate(messageId, ratings, expectedAnswer)
							}
							onClose={() => setRatingPopoverOpen(false)}
						/>
					)}
				</div>
			</div>
		</motion.div>
	);
}

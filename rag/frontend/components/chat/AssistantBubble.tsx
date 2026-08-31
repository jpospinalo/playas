"use client";

import {
	useState,
	useEffect,
	useRef,
	useMemo,
	useCallback,
	useId,
} from "react";
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
	isRated: boolean;
	/** A5 — true si esta respuesta (ya completa) no pudo guardarse en el backend. */
	persistenceFailed?: boolean;
	/** A5 — true mientras un reintento manual de guardado está en curso. */
	retryingPersist?: boolean;
	/** A5 — dispara el reintento manual de guardado. Requerido si `persistenceFailed`. */
	onRetryPersist?: () => void;
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

// Debe coincidir con el `max-width` real que aplica `.doc-popover--rich`
// en globals.css (la variante que este componente usa siempre) — no con el
// `max-width` de la clase base `.doc-popover`, que es distinto, o el
// clamping horizontal asumiría un ancho menor al real y el popover podría
// desbordar el borde derecho del contenedor.
const POPOVER_MAX_WIDTH = 380;
// Separación vertical entre el badge de cita y el popover.
const POPOVER_GAP = 6;
// Aire mínimo respecto al borde inferior del viewport al recortar verticalmente.
const POPOVER_VIEWPORT_MARGIN = 8;

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
	isRated,
	persistenceFailed = false,
	retryingPersist = false,
	onRetryPersist,
	onRate,
}: AssistantBubbleProps) {
	const processedText = useMemo(() => prepareMarkdown(text), [text]);
	const popoverId = useId();

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
	// Badge que abrió el popover actualmente visible, para devolverle el
	// foco al cerrar (Escape, click afuera, o alternar a otra cita).
	const triggerElRef = useRef<HTMLButtonElement | null>(null);

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

	// El popover no es `role="tooltip"` (contenido rico, desplazable,
	// enfocable), así que el foco se gestiona como una divulgación
	// (disclosure) no modal: al abrirse, el foco entra al contenedor del
	// popover para que quede alcanzable por teclado sin depender del orden de
	// tabulación del resto del mensaje; al cerrarse (Escape, click afuera, o
	// alternar a otra cita), el foco vuelve al badge que lo abrió. A
	// diferencia de `useDialog`, deliberadamente NO se atrapa el foco con
	// Tab: el popover no es modal y el usuario debe poder seguir tabulando
	// hacia el resto de la respuesta mientras está abierto.
	useEffect(() => {
		if (popover) {
			popoverElRef.current?.focus();
			return;
		}
		triggerElRef.current?.focus();
	}, [popover]);

	// Recorte vertical: si el popover recién medido se sale por debajo del
	// viewport, se desplaza hacia arriba lo justo para volver a quedar
	// visible (mismo criterio que el clamping horizontal ya existente, que
	// evita que se salga por el borde derecho del contenedor).
	//
	// Ese desplazamiento hacia arriba (o la posición inicial, si el badge
	// que lo abrió ya está cerca del borde superior en un viewport bajo)
	// puede a su vez sacar el popover por ARRIBA del viewport. No basta con
	// evitar que `top` baje de 0 relativo al propio wrapper (`proseRef`),
	// porque eso no dice nada sobre el borde superior REAL del viewport: el
	// wrapper puede empezar más arriba de ese borde (mensaje desplazado
	// dentro del área de chat). `wrapperTop` convierte `nextTop` (relativo
	// al wrapper) a coordenadas de viewport para comprobar el
	// margen superior con el mismo criterio que ya se usa para el inferior.
	// Con el `max-height` del propio popover acotado a `100dvh` (ver
	// `.doc-popover` en globals.css), ambos márgenes son satisfacibles a la
	// vez en la práctica.
	useEffect(() => {
		if (!popover) return;
		const el = popoverElRef.current;
		if (!el) return;

		const rect = el.getBoundingClientRect();
		let nextTop = popover.top;

		const bottomOverflow =
			rect.bottom - (window.innerHeight - POPOVER_VIEWPORT_MARGIN);
		if (bottomOverflow > 0) {
			nextTop -= bottomOverflow;
		}

		const wrapperTop = rect.top - popover.top;
		const topOverflow = POPOVER_VIEWPORT_MARGIN - (wrapperTop + nextTop);
		if (topOverflow > 0) {
			nextTop += topOverflow;
		}

		if (nextTop !== popover.top) {
			setPopover({ ...popover, top: nextTop });
		}
		// Solo depende de qué cita está abierta y de su posición horizontal:
		// una vez recortado el `top`, no debe volver a medirse y ajustarse a
		// sí mismo en bucle.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [popover?.fragmentIndex, popover?.left]);

	// Lectura declarativa: `aria-expanded` se lee directamente de
	// `popoverRef.current` (siempre al día — `setPopover` lo actualiza de
	// forma síncrona, ver arriba) en cada invocación de `a()`, en vez de un
	// efecto imperativo que recorre el DOM. Esto NO añade `popover` a las
	// dependencias del `useMemo` de `components` (ver abajo): la identidad
	// de `a` sigue sin cambiar entre renders, así que React no desmonta el
	// `<button>` al abrir/cerrar. Esto depende empíricamente de que
	// ReactMarkdown vuelva a invocar `a()` en cada re-render de
	// `AssistantBubble` — y en este árbol, sí lo hace: ReactMarkdown no está
	// envuelto en `React.memo`, así que cualquier cambio de estado en
	// `AssistantBubble` (incluido abrir/cerrar `popover`) lo vuelve a
	// renderizar como
	// cualquier otro componente hijo no memoizado, y `remarkPlugins=
	// {[remarkGfm]}` (un array literal nuevo en cada render) impide
	// además cualquier memoización interna por identidad de props que
	// pudiera saltarse ese re-render. Verificado empíricamente con la
	// batería de pruebas existente (incluida la que comprueba que el badge
	// NO se desmonta al alternar el popover): ver AssistantBubble.test.tsx.

	// ReactMarkdown component overrides. Defined with useMemo so the badge
	// render functions aren't recreated on every high-frequency streaming
	// update (`text`/`processedText` changing token by token) NOR on every
	// citation popover open/close (`popover` is deliberately NOT a
	// dependency — ver el efecto de arriba).
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
						// Con `disabled` real (no solo `aria-disabled` + `pointer-events:
						// none` en CSS), el elemento queda fuera del orden de tabulación
						// y el navegador nunca despacha eventos de activación, que es lo
						// que `aria-disabled` por sí solo no garantiza.
						disabled={!hasFragment}
						aria-disabled={!hasFragment}
						// El popover es una divulgación (disclosure) que este botón
						// controla, no un tooltip pasivo. El valor inicial es siempre
						// "false" (recién montado, cerrado); el efecto de arriba lo
						// mantiene sincronizado después. Lectura declarativa (ver
						// comentario arriba, sobre `components`): valor recalculado en
						// cada invocación de `a()` a partir de `popoverRef.current`, no
						// de una prop reactiva.
						aria-expanded={
							hasFragment
								? (popoverRef.current?.fragmentIndex === n ? "true" : "false")
								: undefined
						}
						aria-controls={hasFragment ? popoverId : undefined}
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
							triggerElRef.current = btn;
							const wrapperRect = proseRef.current.getBoundingClientRect();
							const btnRect = btn.getBoundingClientRect();

							setPopover({
								fragmentIndex: n,
								top: btnRect.bottom - wrapperRect.top + POPOVER_GAP,
								left: Math.max(
									0,
									Math.min(
										btnRect.left - wrapperRect.left,
										wrapperRect.width - POPOVER_MAX_WIDTH,
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
		[setPopover, fragmentLookup, popoverId],
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
							id={popoverId}
							role="region"
							className="doc-popover doc-popover--rich"
							tabIndex={-1}
							aria-label={`Fuente ${popover.fragmentIndex}${
								activeTitle ? `: ${activeTitle}` : ""
							}`}
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

							{/* Región desplazable enfocable individualmente
							    (`tabIndex={0}`), para que un usuario de teclado
							    pueda entrar a ella y desplazarse con flechas /
							    Av Pág cuando el contenido del fragmento excede la
							    altura máxima. */}
							<p
								className="doc-popover-content doc-popover-content--scroll"
								tabIndex={0}
							>
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

				{/* A5 — la respuesta ya se generó por completo pero no se pudo
				    guardar: aviso no destructivo (la respuesta sigue visible
				    arriba) + reintento manual, nunca automático. */}
				{persistenceFailed && (
					<div
						role="alert"
						className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger"
					>
						<span>Esta respuesta no se pudo guardar.</span>
						<button
							type="button"
							onClick={() => onRetryPersist?.()}
							disabled={retryingPersist}
							className="font-medium underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-60 disabled:no-underline"
						>
							{retryingPersist ? "Reintentando…" : "Reintentar"}
						</button>
					</div>
				)}

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
							className="inline-flex items-center justify-center rounded-full p-1.5 text-muted transition-colors hover:bg-elevated hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
							aria-label="Calificar esta respuesta"
							title="Calificar esta respuesta"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="20"
								height="20"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2"
								strokeLinecap="round"
								strokeLinejoin="round"
								aria-hidden="true"
							>
								<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
							</svg>
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

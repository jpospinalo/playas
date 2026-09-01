"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/config";
import { restErrorMessage, withRestTimeout } from "@/lib/httpTimeout";
import { throwIfSessionExpired } from "@/lib/api";
import {
	colombiaEndOfDayIso,
	colombiaStartOfDayIso,
	isValidDateRange,
	isValidNumericRange,
} from "@/lib/adminDateRange";

const PAGE_SIZE = 20;

interface RatingDimensions {
	tone: number;
	length: number;
	usability: number;
	overall: number;
}

interface FeedbackItem {
	id: string;
	userId: string;
	userEmail: string;
	ratings: RatingDimensions;
	comment: string | null;
	conversationId: string | null;
	conversationTitle: string | null;
	createdAt: string;
}

interface FeedbackResponse {
	items: FeedbackItem[];
	total: number;
	avg_ratings: RatingDimensions;
	distributions: { overall: Record<string, number> };
}

interface AppliedFilters {
	minOverall: string;
	maxOverall: string;
	startDate: string;
	endDate: string;
}

const EMPTY_FILTERS: AppliedFilters = {
	minOverall: "",
	maxOverall: "",
	startDate: "",
	endDate: "",
};

function Stars({ rating }: { rating: number }) {
	return (
		<span
			className="flex items-center gap-0.5"
			aria-label={`${rating} estrellas`}
		>
			{[1, 2, 3, 4, 5].map((i) => (
				<svg
					key={i}
					xmlns="http://www.w3.org/2000/svg"
					width="13"
					height="13"
					viewBox="0 0 24 24"
					fill={i <= rating ? "currentColor" : "none"}
					stroke="currentColor"
					strokeWidth="1.5"
					className={i <= rating ? "text-accent" : "text-subtle"}
					aria-hidden="true"
				>
					<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
				</svg>
			))}
		</span>
	);
}

function formatDate(iso: string): string {
	if (!iso) return "—";
	try {
		return new Intl.DateTimeFormat("es-CO", {
			dateStyle: "medium",
			timeStyle: "short",
		}).format(new Date(iso));
	} catch {
		return iso;
	}
}

export default function FeedbackPage() {
	const [items, setItems] = useState<FeedbackItem[]>([]);
	const [total, setTotal] = useState(0);
	const [avgRatings, setAvgRatings] = useState<RatingDimensions>({
		tone: 0,
		length: 0,
		usability: 0,
		overall: 0,
	});
	const [page, setPage] = useState(1);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// A3.1 — filtros "borrador" (lo que el usuario está escribiendo/
	// seleccionando) separados de los filtros "aplicados" (lo que realmente
	// se envía al backend). Escribir o seleccionar ya NO dispara ninguna
	// solicitud por sí mismo — solo "Aplicar filtros" lo hace.
	const [draftMinOverall, setDraftMinOverall] = useState<string>("");
	const [draftMaxOverall, setDraftMaxOverall] = useState<string>("");
	const [draftStartDate, setDraftStartDate] = useState("");
	const [draftEndDate, setDraftEndDate] = useState("");
	const [filterError, setFilterError] = useState<string | null>(null);
	const [appliedFilters, setAppliedFilters] =
		useState<AppliedFilters>(EMPTY_FILTERS);

	// A3.5 — controla la cancelación de la solicitud anterior cuando una
	// nueva la reemplaza (cambio de página o de filtros aplicados antes de
	// que la solicitud previa terminara).
	const abortRef = useRef<AbortController | null>(null);

	const totalPages = Math.ceil(total / PAGE_SIZE);

	const load = useCallback(
		async (p: number) => {
			abortRef.current?.abort();
			const controller = new AbortController();
			abortRef.current = controller;

			setLoading(true);
			setError(null);
			try {
				const { expireAuthSession, getToken } = await import("@/lib/auth");
				const token = getToken();
				if (!token) {
					// Página administrativa: solo se llega aquí ya autenticado, así
					// que un token ausente es una sesión perdida en otro lado, no el
					// estado inicial normal. Notifica para que la UI se actualice.
					expireAuthSession(null);
					throw new Error("Sin sesión");
				}

				const params = new URLSearchParams({
					page: String(p),
					page_size: String(PAGE_SIZE),
				});
				if (appliedFilters.minOverall)
					params.set("min_overall", appliedFilters.minOverall);
				if (appliedFilters.maxOverall)
					params.set("max_overall", appliedFilters.maxOverall);
				// A3.7 — interpretadas como día calendario de Colombia (UTC-5),
				// no como medianoche UTC (ver lib/adminDateRange.ts).
				if (appliedFilters.startDate)
					params.set(
						"start_date",
						colombiaStartOfDayIso(appliedFilters.startDate),
					);
				if (appliedFilters.endDate)
					params.set("end_date", colombiaEndOfDayIso(appliedFilters.endDate));

				const res = await fetch(`${API_URL}/api/admin/feedback?${params}`, {
					headers: { Authorization: `Bearer ${token}` },
					signal: withRestTimeout(controller.signal),
				});
				await throwIfSessionExpired(res, token);
				if (!res.ok) throw new Error(`Error ${res.status}`);
				const data: FeedbackResponse = await res.json();
				// Una respuesta obsoleta (ya reemplazada por una solicitud más
				// nueva) no debe pisar el resultado vigente.
				if (abortRef.current !== controller) return;
				setItems(data.items);
				setTotal(data.total);
				setAvgRatings(
					data.avg_ratings ?? { tone: 0, length: 0, usability: 0, overall: 0 },
				);
			} catch (e) {
				// A3.6 — una cancelación deliberada (AbortError) no es un error
				// visible para el usuario, es la consecuencia normal de haber
				// disparado una solicitud más reciente.
				if (e instanceof DOMException && e.name === "AbortError") return;
				if (abortRef.current !== controller) return;
				setError(restErrorMessage(e, "Error desconocido"));
			} finally {
				// Limpia la referencia por identidad: si esta sigue siendo la
				// solicitud vigente, ya terminó y no queda nada que una carga
				// posterior (otra página o filtro) pudiera necesitar cancelar.
				if (abortRef.current === controller) {
					setLoading(false);
					abortRef.current = null;
				}
			}
		},
		[appliedFilters],
	);

	useEffect(() => {
		load(page);
		// G2.1 — aborta la solicitud activa al desmontar o antes de que el
		// efecto se vuelva a ejecutar (cambio de página/filtros), para que
		// una respuesta tardía de un efecto ya reemplazado nunca actualice
		// el estado de un componente desmontado ni pise datos más nuevos.
		return () => {
			abortRef.current?.abort();
		};
	}, [load, page]);

	function applyFilters() {
		// A3.3 — validación antes de disparar la solicitud: mínimo <= máximo,
		// fecha inicial <= fecha final.
		if (!isValidNumericRange(draftMinOverall, draftMaxOverall)) {
			setFilterError("El mínimo general no puede ser mayor que el máximo.");
			return;
		}
		if (!isValidDateRange(draftStartDate, draftEndDate)) {
			setFilterError(
				"La fecha «Desde» no puede ser posterior a la fecha «Hasta».",
			);
			return;
		}
		setFilterError(null);
		setPage(1);
		setAppliedFilters({
			minOverall: draftMinOverall,
			maxOverall: draftMaxOverall,
			startDate: draftStartDate,
			endDate: draftEndDate,
		});
	}

	function clearFilters() {
		setDraftMinOverall("");
		setDraftMaxOverall("");
		setDraftStartDate("");
		setDraftEndDate("");
		setFilterError(null);
		setPage(1);
		setAppliedFilters(EMPTY_FILTERS);
	}

	return (
		<div className="max-w-5xl space-y-6">
			<div>
				<h1 className="text-3xl font-medium tracking-tight text-foreground" style={{ letterSpacing: "-0.02em" }}>
					Calificaciones de conversación
				</h1>
				<p className="mt-1.5 text-sm text-muted">
					{total}{" "}
					{total === 1
						? "calificación registrada"
						: "calificaciones registradas"}
				</p>
				{total > 0 && (
					<div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-subtle">
						<span>Tono · <span className="text-foreground tabular-nums">{avgRatings.tone.toFixed(1)}</span></span>
						<span>Longitud · <span className="text-foreground tabular-nums">{avgRatings.length.toFixed(1)}</span></span>
						<span>Usabilidad · <span className="text-foreground tabular-nums">{avgRatings.usability.toFixed(1)}</span></span>
						<span>General · <span className="text-foreground tabular-nums">{avgRatings.overall.toFixed(1)}</span></span>
					</div>
				)}
			</div>

			<div className="rounded-2xl border border-border bg-elevated/40 p-5 backdrop-blur-sm">
				<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
					<div>
						<label
							htmlFor="fb-min-overall"
							className="mb-1 block text-xs text-subtle"
						>
							General mínimo
						</label>
						<select
							id="fb-min-overall"
							value={draftMinOverall}
							onChange={(e) => setDraftMinOverall(e.target.value)}
							className="w-full rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]"
						>
							<option value="">—</option>
							{[1, 2, 3, 4, 5].map((n) => (
								<option key={n} value={n}>
									{n} ★
								</option>
							))}
						</select>
					</div>
					<div>
						<label
							htmlFor="fb-max-overall"
							className="mb-1 block text-xs text-subtle"
						>
							General máximo
						</label>
						<select
							id="fb-max-overall"
							value={draftMaxOverall}
							onChange={(e) => setDraftMaxOverall(e.target.value)}
							className="w-full rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]"
						>
							<option value="">—</option>
							{[1, 2, 3, 4, 5].map((n) => (
								<option key={n} value={n}>
									{n} ★
								</option>
							))}
						</select>
					</div>
					<div>
						<label
							htmlFor="fb-start-date"
							className="mb-1 block text-xs text-subtle"
						>
							Desde
						</label>
						<input
							id="fb-start-date"
							type="date"
							value={draftStartDate}
							onChange={(e) => setDraftStartDate(e.target.value)}
							className="w-full rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]"
						/>
					</div>
					<div>
						<label
							htmlFor="fb-end-date"
							className="mb-1 block text-xs text-subtle"
						>
							Hasta
						</label>
						<input
							id="fb-end-date"
							type="date"
							value={draftEndDate}
							onChange={(e) => setDraftEndDate(e.target.value)}
							className="w-full rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]"
						/>
					</div>
				</div>
				{filterError && (
					<p role="alert" className="mt-3 text-xs text-danger">
						{filterError}
					</p>
				)}
				<div className="mt-4 flex items-center gap-2">
					<button
						onClick={applyFilters}
						className="rounded-full bg-accent px-4 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
					>
						Aplicar filtros
					</button>
					<button
						onClick={clearFilters}
						className="rounded-full border border-border px-4 py-1.5 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
					>
						Limpiar
					</button>
				</div>
			</div>

			{error ? (
				<div className="rounded-2xl border border-border bg-elevated/40 p-6 text-sm text-muted">
					Error: {error}
				</div>
			) : loading ? (
				<div className="flex items-center justify-center py-16">
					<span className="text-sm text-muted">Cargando…</span>
				</div>
			) : items.length === 0 ? (
				<div className="rounded-2xl border border-border bg-elevated/40 p-8 text-center text-sm text-muted">
					No hay feedback con los filtros seleccionados.
				</div>
			) : (
				<div className="overflow-hidden rounded-2xl border border-border bg-elevated/40 backdrop-blur-sm">
					<div className="overflow-x-auto">
						<table className="min-w-full divide-y divide-border text-sm">
							<caption className="sr-only">
								Calificaciones de conversación registradas
							</caption>
							<thead>
								<tr className="bg-surface/50">
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Fecha</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Usuario</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Tono</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Longitud</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Usabilidad</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">General</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Comentario</th>
									<th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Conversación</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-border">
								{items.map((item) => (
									<tr
										key={item.id}
										className="transition-colors hover:bg-surface/40"
									>
										<td className="whitespace-nowrap px-4 py-3 text-xs text-muted tabular-nums">
											{formatDate(item.createdAt)}
										</td>
										<td className="px-4 py-3 text-xs text-foreground">
											<span className="font-mono">{item.userEmail}</span>
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.tone ?? 0} />
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.length ?? 0} />
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.usability ?? 0} />
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.overall ?? 0} />
										</td>
										<td className="max-w-xs px-4 py-3 text-xs text-muted">
											{item.comment ? (
												<span className="line-clamp-2">{item.comment}</span>
											) : (
												<span className="italic text-subtle">Sin comentario</span>
											)}
										</td>
										<td className="max-w-[180px] px-4 py-3 text-xs text-muted">
											{item.conversationTitle ? (
												<span
													className="block truncate"
													title={item.conversationTitle}
												>
													{item.conversationTitle}
												</span>
											) : (
												<span className="italic text-subtle">—</span>
											)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</div>
			)}

			{totalPages > 1 && (
				<div className="flex items-center justify-between text-xs text-muted">
					<span>
						Página {page} de {totalPages} · {total} total
					</span>
					<div className="flex items-center gap-2">
						<button
							onClick={() => setPage((p) => Math.max(1, p - 1))}
							disabled={page === 1}
							className="rounded-full border border-border px-3 py-1 transition-colors hover:bg-elevated hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
						>
							← Anterior
						</button>
						<button
							onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
							disabled={page === totalPages}
							className="rounded-full border border-border px-3 py-1 transition-colors hover:bg-elevated hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
						>
							Siguiente →
						</button>
					</div>
				</div>
			)}
		</div>
	);
}

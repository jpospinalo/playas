"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";
const PAGE_SIZE = 20;

interface MessageRatings {
	pertinence: number;
	accuracy: number;
}

interface MessageFeedbackItem {
	id: string;
	userId: string;
	userEmail: string;
	conversationId: string;
	messageId: string;
	ratings: MessageRatings;
	expectedAnswer: string | null;
	createdAt: string;
}

interface MessageFeedbackResponse {
	items: MessageFeedbackItem[];
	total: number;
	avg_ratings: { pertinence: number; accuracy: number };
	distributions: {
		pertinence: Record<string, number>;
		accuracy: Record<string, number>;
	};
}

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
					className={i <= rating ? "text-accent" : "text-border"}
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

function truncate(text: string | null, maxLen: number = 50): string {
	if (!text) return "—";
	return text.length > maxLen ? text.slice(0, maxLen) + "…" : text;
}

export default function MessageFeedbackPage() {
	const [items, setItems] = useState<MessageFeedbackItem[]>([]);
	const [total, setTotal] = useState(0);
	const [page, setPage] = useState(1);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// Filtros
	const [minPertinence, setMinPertinence] = useState<string>("");
	const [maxPertinence, setMaxPertinence] = useState<string>("");
	const [minAccuracy, setMinAccuracy] = useState<string>("");
	const [maxAccuracy, setMaxAccuracy] = useState<string>("");
	const [startDate, setStartDate] = useState("");
	const [endDate, setEndDate] = useState("");

	// Expanding expected answer
	const [expandedId, setExpandedId] = useState<string | null>(null);

	const totalPages = Math.ceil(total / PAGE_SIZE);

	const load = useCallback(
		async (p: number) => {
			setLoading(true);
			setError(null);
			try {
				const { auth } = await import("@/lib/firebase");
				const token = await auth.currentUser?.getIdToken(true);
				if (!token) throw new Error("Sin sesión");

				const params = new URLSearchParams({
					page: String(p),
					page_size: String(PAGE_SIZE),
				});
				if (minPertinence) params.set("min_pertinence", minPertinence);
				if (maxPertinence) params.set("max_pertinence", maxPertinence);
				if (minAccuracy) params.set("min_accuracy", minAccuracy);
				if (maxAccuracy) params.set("max_accuracy", maxAccuracy);
				if (startDate)
					params.set("start_date", new Date(startDate).toISOString());
				if (endDate) params.set("end_date", new Date(endDate).toISOString());

				const res = await fetch(
					`${API_URL}/api/admin/message-feedback?${params}`,
					{
						headers: { Authorization: `Bearer ${token}` },
					},
				);
				if (!res.ok) throw new Error(`Error ${res.status}`);
				const data: MessageFeedbackResponse = await res.json();
				setItems(data.items);
				setTotal(data.total);
			} catch (e) {
				setError(e instanceof Error ? e.message : "Error desconocido");
			} finally {
				setLoading(false);
			}
		},
		[
			minPertinence,
			maxPertinence,
			minAccuracy,
			maxAccuracy,
			startDate,
			endDate,
		],
	);

	useEffect(() => {
		load(page);
	}, [load, page]);

	function applyFilters() {
		setPage(1);
		load(1);
	}

	function clearFilters() {
		setMinPertinence("");
		setMaxPertinence("");
		setMinAccuracy("");
		setMaxAccuracy("");
		setStartDate("");
		setEndDate("");
		setPage(1);
	}

	return (
		<div className="max-w-5xl space-y-6">
			<div>
				<h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground">
					Calificaciones por mensaje
				</h1>
				<p className="mt-1 text-sm text-muted">
					{total}{" "}
					{total === 1
						? "calificación registrada"
						: "calificaciones registradas"}
				</p>
			</div>

			{/* Filtros */}
			<div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
				<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
					<div>
						<label className="block text-xs text-muted mb-1">
							Pertinencia mín
						</label>
						<select
							value={minPertinence}
							onChange={(e) => setMinPertinence(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
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
						<label className="block text-xs text-muted mb-1">
							Pertinencia máx
						</label>
						<select
							value={maxPertinence}
							onChange={(e) => setMaxPertinence(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
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
						<label className="block text-xs text-muted mb-1">
							Precisión mín
						</label>
						<select
							value={minAccuracy}
							onChange={(e) => setMinAccuracy(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
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
						<label className="block text-xs text-muted mb-1">
							Precisión máx
						</label>
						<select
							value={maxAccuracy}
							onChange={(e) => setMaxAccuracy(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
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
						<label className="block text-xs text-muted mb-1">Desde</label>
						<input
							type="date"
							value={startDate}
							onChange={(e) => setStartDate(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
						/>
					</div>
					<div>
						<label className="block text-xs text-muted mb-1">Hasta</label>
						<input
							type="date"
							value={endDate}
							onChange={(e) => setEndDate(e.target.value)}
							className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
						/>
					</div>
				</div>
				<div className="mt-3 flex items-center gap-2">
					<button
						onClick={applyFilters}
						className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1"
					>
						Aplicar filtros
					</button>
					<button
						onClick={clearFilters}
						className="rounded-md border border-border px-3 py-1.5 text-xs text-muted hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus-visible:ring-offset-1"
					>
						Limpiar
					</button>
				</div>
			</div>

			{/* Tabla */}
			{error ? (
				<div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
					Error: {error}
				</div>
			) : loading ? (
				<div className="flex items-center justify-center py-16">
					<span className="text-sm text-muted">Cargando…</span>
				</div>
			) : items.length === 0 ? (
				<div className="rounded-lg border border-border bg-surface p-8 text-center text-sm text-muted">
					No hay calificaciones por mensaje con los filtros seleccionados.
				</div>
			) : (
				<div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
					<div className="overflow-x-auto">
						<table className="min-w-full divide-y divide-border text-sm">
							<thead>
								<tr className="bg-background">
									<th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
										Fecha
									</th>
									<th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
										Usuario
									</th>
									<th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
										Pertinencia
									</th>
									<th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
										Precisión
									</th>
									<th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
										Respuesta esperada
									</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-border">
								{items.map((item) => (
									<tr
										key={item.id}
										className="hover:bg-background/50 transition-colors"
									>
										<td className="whitespace-nowrap px-4 py-3 text-xs text-muted tabular-nums">
											{formatDate(item.createdAt)}
										</td>
										<td className="px-4 py-3 text-xs text-foreground">
											<span className="font-mono">{item.userEmail}</span>
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.pertinence ?? 0} />
										</td>
										<td className="px-4 py-3">
											<Stars rating={item.ratings?.accuracy ?? 0} />
										</td>
										<td className="px-4 py-3 text-xs text-muted max-w-xs">
											{item.expectedAnswer ? (
												expandedId === item.id ? (
													<span>
														{item.expectedAnswer}{" "}
														<button
															onClick={() => setExpandedId(null)}
															className="text-accent hover:underline"
														>
															Ver menos
														</button>
													</span>
												) : (
													<span>
														{truncate(item.expectedAnswer)}{" "}
														{item.expectedAnswer.length > 50 && (
															<button
																onClick={() => setExpandedId(item.id)}
																className="text-accent hover:underline"
															>
																Ver más
															</button>
														)}
													</span>
												)
											) : (
												<span className="italic text-border">—</span>
											)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</div>
			)}

			{/* Paginación */}
			{totalPages > 1 && (
				<div className="flex items-center justify-between text-xs text-muted">
					<span>
						Página {page} de {totalPages} · {total} total
					</span>
					<div className="flex items-center gap-1">
						<button
							onClick={() => setPage((p) => Math.max(1, p - 1))}
							disabled={page === 1}
							className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40 hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-accent"
						>
							← Anterior
						</button>
						<button
							onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
							disabled={page === totalPages}
							className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40 hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-accent"
						>
							Siguiente →
						</button>
					</div>
				</div>
			)}
		</div>
	);
}

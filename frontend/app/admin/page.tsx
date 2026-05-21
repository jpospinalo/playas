"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

interface ConversationFeedbackStats {
	total: number;
	avg_ratings: {
		tone: number;
		length: number;
		usability: number;
		overall: number;
	};
	distributions: { overall: Record<string, number> };
}

interface MessageFeedbackStats {
	total: number;
	avg_ratings: { pertinence: number; accuracy: number };
	distributions: {
		pertinence: Record<string, number>;
		accuracy: Record<string, number>;
	};
}

function StarRating({ value }: { value: number }) {
	return (
		<span
			className="flex items-center gap-0.5"
			aria-label={`${value} de 5 estrellas`}
		>
			{[1, 2, 3, 4, 5].map((i) => (
				<svg
					key={i}
					xmlns="http://www.w3.org/2000/svg"
					width="16"
					height="16"
					viewBox="0 0 24 24"
					fill={i <= Math.round(value) ? "currentColor" : "none"}
					stroke="currentColor"
					strokeWidth="1.5"
					className={i <= Math.round(value) ? "text-accent" : "text-border"}
					aria-hidden="true"
				>
					<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
				</svg>
			))}
		</span>
	);
}

function DistributionBar({
	label,
	distribution,
	total,
}: {
	label: string;
	distribution: Record<string, number>;
	total: number;
}) {
	const maxCount = Math.max(...Object.values(distribution), 1);
	return (
		<div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
			<p className="mb-3 text-xs uppercase tracking-wider text-muted font-medium">
				{label}
			</p>
			<div className="space-y-2">
				{[5, 4, 3, 2, 1].map((star) => {
					const count = distribution[String(star)] ?? 0;
					const pct = total > 0 ? (count / total) * 100 : 0;
					const barPct = maxCount > 0 ? (count / maxCount) * 100 : 0;
					return (
						<div key={star} className="flex items-center gap-3">
							<span className="w-14 shrink-0 text-right text-xs text-muted tabular-nums">
								{star} ★
							</span>
							<div className="flex-1 overflow-hidden rounded-full bg-border h-2">
								<div
									className="h-2 rounded-full bg-accent transition-all duration-500"
									style={{ width: `${barPct}%` }}
								/>
							</div>
							<span className="w-16 shrink-0 text-xs text-muted tabular-nums">
								{count} ({pct.toFixed(0)}%)
							</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

async function fetchConversationStats(
	token: string,
): Promise<ConversationFeedbackStats> {
	const res = await fetch(`${API_URL}/api/admin/feedback?page=1&page_size=1`, {
		headers: { Authorization: `Bearer ${token}` },
	});
	if (!res.ok) throw new Error(`Error ${res.status}`);
	const data = await res.json();
	return {
		total: data.total,
		avg_ratings: data.avg_ratings ?? {
			tone: 0,
			length: 0,
			usability: 0,
			overall: 0,
		},
		distributions: data.distributions ?? {
			overall: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
		},
	};
}

async function fetchMessageStats(token: string): Promise<MessageFeedbackStats> {
	const res = await fetch(
		`${API_URL}/api/admin/message-feedback?page=1&page_size=1`,
		{
			headers: { Authorization: `Bearer ${token}` },
		},
	);
	// 404 means no message feedback yet — return zeros
	if (res.status === 404) {
		return {
			total: 0,
			avg_ratings: { pertinence: 0, accuracy: 0 },
			distributions: {
				pertinence: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
				accuracy: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
			},
		};
	}
	if (!res.ok) throw new Error(`Error ${res.status}`);
	const data = await res.json();
	return {
		total: data.total,
		avg_ratings: data.avg_ratings ?? { pertinence: 0, accuracy: 0 },
		distributions: data.distributions ?? {
			pertinence: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
			accuracy: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
		},
	};
}

export default function AdminPage() {
	const [convStats, setConvStats] = useState<ConversationFeedbackStats | null>(
		null,
	);
	const [msgStats, setMsgStats] = useState<MessageFeedbackStats | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		async function load() {
			try {
				const { auth } = await import("@/lib/firebase");
				const token = await auth.currentUser?.getIdToken(true);
				if (!token) throw new Error("Sin sesión");
				const [cs, ms] = await Promise.all([
					fetchConversationStats(token),
					fetchMessageStats(token),
				]);
				setConvStats(cs);
				setMsgStats(ms);
			} catch (e) {
				setError(e instanceof Error ? e.message : "Error desconocido");
			} finally {
				setLoading(false);
			}
		}
		load();
	}, []);

	if (loading) {
		return (
			<div className="flex items-center justify-center py-24">
				<span className="text-sm text-muted">Cargando estadísticas…</span>
			</div>
		);
	}

	if (error) {
		return (
			<div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
				Error cargando estadísticas: {error}
			</div>
		);
	}

	return (
		<div className="max-w-3xl space-y-8">
			<div>
				<h1 className="font-display text-2xl font-semibold text-foreground">
					Resumen
				</h1>
				<p className="mt-1 text-sm text-muted">
					Estadísticas generales del sistema de feedback.
				</p>
			</div>

			{/* Calificaciones de conversación */}
			{convStats && (
				<section>
					<h2 className="mb-3 text-lg font-semibold text-foreground">
						Calificaciones de conversación
					</h2>
					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
							<p className="text-xs uppercase tracking-wider text-muted font-medium">
								Total de calificaciones
							</p>
							<p className="mt-2 text-4xl font-bold text-foreground tabular-nums">
								{convStats.total}
							</p>
						</div>
						<div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
							<p className="text-xs uppercase tracking-wider text-muted font-medium">
								Promedio general
							</p>
							<div className="mt-2 flex items-end gap-2">
								<span className="text-4xl font-bold text-foreground tabular-nums">
									{convStats.avg_ratings.overall.toFixed(1)}
								</span>
								<span className="mb-1 text-sm text-muted">/ 5</span>
							</div>
							<div className="mt-1">
								<StarRating value={convStats.avg_ratings.overall} />
							</div>
						</div>
					</div>
					<div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
						{(
							[
								["Tono", convStats.avg_ratings.tone],
								["Longitud", convStats.avg_ratings.length],
								["Usabilidad", convStats.avg_ratings.usability],
								["General", convStats.avg_ratings.overall],
							] as const
						).map(([label, val]) => (
							<div
								key={label}
								className="rounded-lg border border-border bg-surface p-3 shadow-sm text-center"
							>
								<p className="text-xs text-muted">{label}</p>
								<p className="mt-1 text-lg font-bold text-foreground tabular-nums">
									{val.toFixed(1)}
								</p>
							</div>
						))}
					</div>
					{convStats.distributions.overall && (
						<div className="mt-4">
							<DistributionBar
								label="Distribución general"
								distribution={convStats.distributions.overall}
								total={convStats.total}
							/>
						</div>
					)}
				</section>
			)}

			{/* Calificaciones por mensaje */}
			{msgStats && (
				<section>
					<h2 className="mb-3 text-lg font-semibold text-foreground">
						Calificaciones por mensaje
					</h2>
					<div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
							<p className="text-xs uppercase tracking-wider text-muted font-medium">
								Total de calificaciones
							</p>
							<p className="mt-2 text-4xl font-bold text-foreground tabular-nums">
								{msgStats.total}
							</p>
						</div>
						<div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
							<p className="text-xs uppercase tracking-wider text-muted font-medium">
								Avg Pertinencia
							</p>
							<div className="mt-2 flex items-end gap-2">
								<span className="text-4xl font-bold text-foreground tabular-nums">
									{msgStats.avg_ratings.pertinence.toFixed(1)}
								</span>
								<span className="mb-1 text-sm text-muted">/ 5</span>
							</div>
							<div className="mt-1">
								<StarRating value={msgStats.avg_ratings.pertinence} />
							</div>
						</div>
						<div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
							<p className="text-xs uppercase tracking-wider text-muted font-medium">
								Avg Precisión
							</p>
							<div className="mt-2 flex items-end gap-2">
								<span className="text-4xl font-bold text-foreground tabular-nums">
									{msgStats.avg_ratings.accuracy.toFixed(1)}
								</span>
								<span className="mb-1 text-sm text-muted">/ 5</span>
							</div>
							<div className="mt-1">
								<StarRating value={msgStats.avg_ratings.accuracy} />
							</div>
						</div>
					</div>
					<div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
						<DistributionBar
							label="Distribución pertinencia"
							distribution={msgStats.distributions.pertinence}
							total={msgStats.total}
						/>
						<DistributionBar
							label="Distribución precisión"
							distribution={msgStats.distributions.accuracy}
							total={msgStats.total}
						/>
					</div>
				</section>
			)}
		</div>
	);
}

"use client";

import { useEffect, useState } from "react";
import type { Metadata } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

interface FeedbackStats {
  total: number;
  avg_rating: number;
  distribution: Record<string, number>;
}

function StarRating({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-label={`${value} de 5 estrellas`}>
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

async function fetchStats(token: string): Promise<FeedbackStats> {
  const res = await fetch(`${API_URL}/api/admin/feedback?page=1&page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  const data = await res.json();
  return {
    total: data.total,
    avg_rating: data.avg_rating,
    distribution: data.distribution,
  };
}

export default function AdminPage() {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const { auth } = await import("@/lib/firebase");
        const token = await auth.currentUser?.getIdToken(true);
        if (!token) throw new Error("Sin sesión");
        const s = await fetchStats(token);
        setStats(s);
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

  if (error || !stats) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
        Error cargando estadísticas: {error}
      </div>
    );
  }

  const maxCount = Math.max(...Object.values(stats.distribution), 1);

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground">
          Resumen
        </h1>
        <p className="mt-1 text-sm text-muted">
          Estadísticas generales del sistema de feedback.
        </p>
      </div>

      {/* Tarjetas de métricas */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <p className="text-xs uppercase tracking-wider text-muted font-medium">
            Total de calificaciones
          </p>
          <p className="mt-2 text-4xl font-bold text-foreground tabular-nums">
            {stats.total}
          </p>
        </div>

        <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <p className="text-xs uppercase tracking-wider text-muted font-medium">
            Promedio
          </p>
          <div className="mt-2 flex items-end gap-2">
            <span className="text-4xl font-bold text-foreground tabular-nums">
              {stats.avg_rating.toFixed(1)}
            </span>
            <span className="mb-1 text-sm text-muted">/ 5</span>
          </div>
          <div className="mt-1">
            <StarRating value={stats.avg_rating} />
          </div>
        </div>
      </div>

      {/* Distribución */}
      <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <p className="text-xs uppercase tracking-wider text-muted font-medium mb-4">
          Distribución de calificaciones
        </p>
        <div className="space-y-2.5">
          {[5, 4, 3, 2, 1].map((star) => {
            const count = stats.distribution[String(star)] ?? 0;
            const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
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
    </div>
  );
}

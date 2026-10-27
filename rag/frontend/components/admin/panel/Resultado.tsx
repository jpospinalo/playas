"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { mensajeError } from "@/lib/admin/panel";
import { AparecerSi } from "@/components/admin/panel/Aparece";

/**
 * J6-A1: el resultado de un clic se ve donde está el botón.
 *
 * - `useAccion` corre la acción: el botón dice "Guardando…", luego
 *   "Guardado ✓" durante 2,5 s, y debajo queda el resultado (✓ en verde).
 * - Los errores quedan debajo del botón, fijos, hasta que la acción salga bien.
 * - Con `lejos`, además sale un aviso fijo abajo de la pantalla (toast), para
 *   lo que cambia en otra parte (una fila que se mueve, una lista que se recarga).
 */

export type Resultado = { tipo: "ok" | "error"; texto: ReactNode };

const HECHO_MS = 2500;

export function useAccion() {
	const [estado, setEstado] = useState<"listo" | "enviando" | "hecho">("listo");
	const [resultado, setResultado] = useState<Resultado | null>(null);
	const avisar = useAvisar();

	useEffect(() => {
		if (estado !== "hecho") return;
		const t = setTimeout(() => setEstado("listo"), HECHO_MS);
		return () => clearTimeout(t);
	}, [estado]);

	const correr = useCallback(
		async (
			accion: () => Promise<ReactNode | void>,
			opciones: { error?: string; lejos?: boolean } = {},
		): Promise<boolean> => {
			setEstado("enviando");
			try {
				const texto = await accion();
				setResultado(texto ? { tipo: "ok", texto } : null);
				setEstado("hecho");
				if (opciones.lejos && texto) avisar({ tipo: "ok", texto });
				return true;
			} catch (e) {
				setResultado({ tipo: "error", texto: mensajeError(e, opciones.error ?? "No se pudo guardar.") });
				setEstado("listo");
				return false;
			}
		},
		[avisar],
	);

	/** Quita el resultado (por ejemplo, al cancelar). */
	const limpiar = useCallback(() => setResultado(null), []);

	return { estado, resultado, correr, limpiar, enviando: estado === "enviando" };
}

/** Texto del botón según el estado: "Guardar" → "Guardando…" → "Guardado ✓". */
export function textoBoton(
	estado: "listo" | "enviando" | "hecho",
	textos: { listo: string; enviando?: string; hecho?: string },
): string {
	if (estado === "enviando") return textos.enviando ?? "Guardando…";
	if (estado === "hecho") return `${textos.hecho ?? "Guardado"} ✓`;
	return textos.listo;
}

/** El resultado junto al botón: ✓ texto, o el error fijo hasta corregirlo. */
export function ResultadoJunto({ resultado, id }: { resultado: Resultado | null; id?: string }) {
	return (
		<AparecerSi valor={resultado}>
			{(r) =>
				r.tipo === "ok" ? (
					<p id={id} className="pnl-resultado bien" role="status">
						<span aria-hidden="true">✓</span> {r.texto}
					</p>
				) : (
					<p id={id} className="pnl-resultado mal" role="alert">
						{r.texto}
					</p>
				)
			}
		</AparecerSi>
	);
}

// ── Aviso fijo abajo de la pantalla (toast) ───────────────────────────────

type Aviso = Resultado & { id: number };
const AvisosCtx = createContext<(a: Resultado) => void>(() => {});

export function useAvisar() {
	return useContext(AvisosCtx);
}

export function AvisosProvider({ children }: { children: ReactNode }) {
	const [avisos, setAvisos] = useState<Aviso[]>([]);
	const sig = useRef(0);
	const quitar = useCallback((id: number) => setAvisos((l) => l.filter((a) => a.id !== id)), []);
	const avisar = useCallback(
		(a: Resultado) => {
			sig.current += 1;
			const id = sig.current;
			setAvisos((l) => [...l.slice(-2), { ...a, id }]);
			// Lo bueno se va solo; los errores quedan hasta cerrarlos.
			if (a.tipo === "ok") setTimeout(() => quitar(id), 5000);
		},
		[quitar],
	);
	return (
		<AvisosCtx.Provider value={avisar}>
			{children}
			<div className="pnl-toasts" role="status" aria-live="polite">
				{avisos.map((a) => (
					<div key={a.id} className={`pnl-toast ${a.tipo === "ok" ? "bien" : "mal"}`}>
						<p>
							{a.tipo === "ok" ? <span aria-hidden="true">✓ </span> : null}
							{a.texto}
						</p>
						<button type="button" className="pnl-enlace" onClick={() => quitar(a.id)}>
							Cerrar<span className="sr"> aviso</span>
						</button>
					</div>
				))}
			</div>
		</AvisosCtx.Provider>
	);
}

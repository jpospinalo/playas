"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { mensajeError, numero, recortar } from "@/lib/admin/panel";
import { TIPOS_PLAYA } from "@/lib/admin/cuentas";
import {
	NIVELES,
	archivarPractica,
	pedirBandeja,
	pedirPractica,
	rolComite,
	type Bandeja,
	type Ct,
	type EstadoPractica,
	type FiltroBandeja,
} from "@/lib/admin/evaluacion";
import { EstadoEval } from "@/components/admin/evaluacion/EstadoEval";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { SubNavEvaluacion } from "@/components/admin/evaluacion/SubNav";

const POR_PAGINA = 20;

/**
 * Bandeja de evaluación: las preguntas de los participantes, anónimas
 * (número y tipo de usuario de playa). Para un semillerista, "Pendientes" son
 * las que puede calificar (nadie de su sede lo hizo); para el comité, las que
 * tienen diferencias sin resolver.
 */
export default function PaginaBandeja() {
	const { role } = useAuth();
	const comite = rolComite(role);
	// "?estado=por_validar" (enlace desde "Faltan N por validar") abre esa pestaña.
	// La bandeja solo se pinta en el navegador (tras confirmar la sesión).
	const [estado, setEstado] = useState<FiltroBandeja>(() =>
		comite && typeof window !== "undefined" && new URLSearchParams(window.location.search).get("estado") === "por_validar"
			? "por_validar"
			: comite
				? "con_diferencias"
				: "pendientes",
	);
	const [tipo, setTipo] = useState(0);
	const [ct, setCt] = useState<Ct | "">("");
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<Bandeja | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);

	useEffect(() => {
		let vigente = true;
		pedirBandeja(estado, tipo, ct, pagina, POR_PAGINA)
			.then((r) => {
				if (vigente) {
					setDatos(r);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las preguntas."));
			});
		return () => {
			vigente = false;
		};
	}, [estado, tipo, ct, pagina, intento]);

	// Comité: lo que debe resolver (diferencias); semillerista: lo que le toca.
	const pestanas: { valor: FiltroBandeja; texto: string }[] = comite
		? [
				{ valor: "con_diferencias", texto: "Con diferencias: por resolver" },
				{ valor: "por_validar", texto: "Concordantes: por validar" },
				{ valor: "finalizadas", texto: "Con calificación oficial" },
				{ valor: "todas", texto: "Todas" },
			]
		: [
				// T1: el semillerista solo ve las preguntas que el sistema le asignó.
				{ valor: "pendientes", texto: "Asignadas sin evaluar" },
				{ valor: "mias", texto: "Ya evaluadas" },
				{ valor: "con_diferencias", texto: "Con diferencias" },
				{ valor: "finalizadas", texto: "Con calificación oficial" },
				{ valor: "todas", texto: "Todas mis asignadas" },
			];

	const total = datos?.total ?? 0;
	const ultima = Math.max(1, Math.ceil(total / POR_PAGINA));

	return (
		<div className="pnl-pag">
			<title>Evaluación de preguntas: panel de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Evaluación de preguntas</h1>
					<p className="pnl-sub">
						{comite
							? "Cada pregunta la evalúan dos semilleristas, uno de Santa Marta y uno de Barranquilla, que el sistema asigna solo."
							: "El sistema le asigna preguntas automáticamente, repartidas por igual entre los semilleristas de su sede."}{" "}
						Califique con la planilla: forma (F1, F2, F3) y fondo (Ct y Cv). Las preguntas son anónimas: solo se
						ve el número del participante y su tipo de usuario de playa.
					</p>
				</div>
			</div>
			<SubNavEvaluacion />
			{comite ? <Practica /> : null}

			<section className="pnl-bloque" aria-labelledby="t-bandeja">
				<div className="pnl-bloque-cab">
					<h2 id="t-bandeja">Preguntas</h2>
					<div className="pnl-controles">
						<div className="pnl-campo">
							<label htmlFor="b-tipo">Tipo de usuario de playa</label>
							<select
								id="b-tipo"
								value={tipo}
								onChange={(e) => {
									setTipo(Number(e.target.value));
									setPagina(1);
								}}
							>
								<option value={0}>Todos</option>
								{TIPOS_PLAYA.map((t) => (
									<option key={t.id} value={t.id}>
										{t.id}. {t.nombre}
									</option>
								))}
							</select>
						</div>
						<div className="pnl-campo">
							<label htmlFor="b-nivel">Nivel (calificación oficial)</label>
							<select
								id="b-nivel"
								value={ct}
								onChange={(e) => {
									setCt(e.target.value as Ct | "");
									setPagina(1);
								}}
							>
								<option value="">Todos</option>
								{(Object.keys(NIVELES) as Ct[]).map((k) => (
									<option key={k} value={k}>
										{k}: {NIVELES[k]}
									</option>
								))}
							</select>
						</div>
					</div>
				</div>

				<div className="pnl-pestanas" role="group" aria-label="Qué preguntas mostrar">
					{pestanas.map((p) => (
						<button
							key={p.valor}
							type="button"
							aria-pressed={estado === p.valor}
							onClick={() => {
								setEstado(p.valor);
								setPagina(1);
							}}
						>
							{p.texto}
							{datos ? <span className="pnl-pestana-n num">{numero(datos.conteos[p.valor] ?? 0)}</span> : null}
						</button>
					))}
				</div>

				{error ? (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudieron cargar las preguntas.</b>
							<p>{error}</p>
							<button type="button" className="pnl-btn-sec" onClick={() => setIntento((n) => n + 1)}>
								Intentar otra vez
							</button>
						</div>
					</div>
				) : null}
				{!datos && !error ? <p className="pnl-cargando">Cargando preguntas…</p> : null}
				{datos && datos.items.length === 0 ? (
					<p className="pnl-vacio">
						<b>No hay preguntas aquí.</b>
						{estado === "pendientes" && !comite
							? "Ya calificó todo lo que le corresponde. Revise “Todas” para ver el avance."
							: "Pruebe con otra pestaña o quite los filtros."}
					</p>
				) : null}

				{datos && datos.items.length ? (
					<ol className="pnl-filas" aria-label="Preguntas para calificar">
						{datos.items.map((p) => (
							<li key={p.message_id} className="pnl-fila">
								<div className="pnl-fila-q">
									<Link href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(p.message_id)}`}>
										<span className="pnl-num-preg">Pregunta {p.numero}.</span> {recortar(p.pregunta, 220)}
									</Link>
									<p className="pnl-fila-meta">
										<span className="pnl-etq">{p.codigo}</span>
										{p.practica ? <span className="pnl-practica">Práctica: no cuenta</span> : null}
										<span>{p.tipo_playa_nombre ?? "Sin tipo"}</span>
										<span>
											{p.fecha}, {p.hora}
										</span>
									</p>
								</div>
								<dl className="pnl-fila-estado">
									<div>
										<dt>Estado</dt>
										<dd>
											<EstadoEval estado={p.estado} />
										</dd>
									</div>
									<div>
										<dt>Calificadas</dt>
										<dd>
											{p.evaluaciones} de 2{p.evaluada_por_mi ? " (una es suya)" : ""}
										</dd>
									</div>
									{p.oficial.total !== null ? (
										<div>
											<dt>Oficial</dt>
											<dd className="pnl-veces">
												{p.oficial.ct ? `${NIVELES[p.oficial.ct]}, ` : ""}
												{p.oficial.total} puntos
												{p.oficial.valida === false ? " (no válida)" : ""}
											</dd>
										</div>
									) : null}
								</dl>
							</li>
						))}
					</ol>
				) : null}

				{datos && total > POR_PAGINA ? (
					<nav className="pnl-pagin" aria-label="Páginas de preguntas">
						<span>
							{numero((pagina - 1) * POR_PAGINA + 1)} a {numero(Math.min(pagina * POR_PAGINA, total))} de{" "}
							{numero(total)}
						</span>
						<div>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={pagina <= 1}
								onClick={() => setPagina((n) => n - 1)}
							>
								Anteriores
							</button>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={pagina >= ultima}
								onClick={() => setPagina((n) => n + 1)}
							>
								Siguientes
							</button>
						</div>
					</nav>
				) : null}
			</section>
		</div>
	);
}

/**
 * T7 (reunión del 20-oct): la semana antes del 2 nov se prueba con cuentas de
 * práctica. Sus preguntas no cuentan; el administrador las archiva al empezar.
 */
function Practica() {
	const { role } = useAuth();
	const esAdmin = role === "admin" || role === "super-admin";
	const [estado, setEstado] = useState<EstadoPractica | null>(null);
	const [confirmar, setConfirmar] = useState(false);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		pedirPractica()
			.then((e) => {
				if (vigente) setEstado(e);
			})
			.catch(() => {
				// Sin el estado de la práctica no se muestra el aviso.
			});
		return () => {
			vigente = false;
		};
	}, []);

	if (!estado || (!estado.cuentas && !estado.archivada)) return null;

	async function cambiar(archivar: boolean) {
		setError(null);
		try {
			setEstado(await archivarPractica(archivar));
			setConfirmar(false);
		} catch (e) {
			setError(mensajeError(e, "No se pudo cambiar la práctica."));
		}
	}

	return (
		<section className="pnl-bloque" aria-labelledby="t-practica">
			<h2 id="t-practica">Práctica</h2>
			<p>
				{estado.archivada
					? "La práctica está archivada: sus preguntas ya no se ven en ninguna lista."
					: `Hay ${numero(estado.cuentas)} cuentas de práctica con ${numero(estado.preguntas)} preguntas. Se evalúan y validan igual, pero no cuentan para el resumen, los premios ni el Excel.`}
			</p>
			{error ? (
				<p className="pnl-error-linea" role="alert">
					{error}
				</p>
			) : null}
			{esAdmin ? (
				confirmar ? (
					<div className="pnl-confirmar" role="group" aria-labelledby="t-arch">
						<p id="t-arch">
							¿Archivar la práctica? Sus preguntas salen de todas las listas; no se borra nada y se puede deshacer.
						</p>
						<div className="pnl-acciones">
							<button type="button" className="pnl-btn" onClick={() => cambiar(true)}>
								Sí, archivar
							</button>
							<button type="button" className="pnl-btn-sec" onClick={() => setConfirmar(false)}>
								Cancelar
							</button>
						</div>
					</div>
				) : estado.archivada ? (
					<button type="button" className="pnl-btn-sec" onClick={() => cambiar(false)}>
						Volver a mostrar la práctica
					</button>
				) : (
					<button type="button" className="pnl-btn-sec" onClick={() => setConfirmar(true)}>
						Archivar la práctica
					</button>
				)
			) : null}
		</section>
	);
}


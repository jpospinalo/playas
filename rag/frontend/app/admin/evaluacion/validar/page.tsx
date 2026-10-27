"use client";

import { useEffect, useState } from "react";
import { cuantas, diaMesCalendario, mensajeError, numero } from "@/lib/admin/panel";
import { NIVELES } from "@/lib/admin/evaluacion";
import {
	TEXTO_VALIDACION,
	deAcuerdoEnLote,
	marcarPertinencia,
	pedirBandejaValidacion,
	pedirDetalle,
	validarEvaluacion,
	type BandejaValidacion,
	type DetalleEvaluacion,
	type EvaluacionV,
	type FiltroValidacion,
	type ItemValidacion,
} from "@/lib/admin/validacion";
import { ChipNivel, ChipEstado, IconoAviso } from "@/components/admin/panel/Estados";
import { ResultadoJunto, useAccion } from "@/components/admin/panel/Resultado";
import { CabezaPestana, EncabezadoEvaluacion } from "@/components/admin/evaluacion/SubNav";
import { Hilo } from "@/components/admin/evaluacion/Hilo";
import { Aparece, AparecerSi } from "@/components/admin/panel/Aparece";
import { LimpiarFiltros } from "@/components/admin/panel/LimpiarFiltros";

const POR_PAGINA = 20;

/**
 * Validación (reunión del 20-oct): Ana María y Sandra validan cada evaluación
 * de su sede (de acuerdo / no y conversación); Camilo marca si cada pregunta
 * es del tema de playas. El administrador solo mira.
 */
export default function PaginaValidar() {
	const [estado, setEstado] = useState<FiltroValidacion>("por_validar");
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<BandejaValidacion | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [recarga, setRecarga] = useState(0);
	const [elegidas, setElegidas] = useState<Set<string>>(new Set());
	const [confirmar, setConfirmar] = useState(false);
	const accLote = useAccion();
	// PQ-91: buscar y ver primero las más recientes.
	const [borrador, setBorrador] = useState("");
	const [buscar, setBuscar] = useState("");
	const [orden, setOrden] = useState<"antiguas" | "recientes">("recientes");

	useEffect(() => {
		let vigente = true;
		pedirBandejaValidacion(estado, pagina, POR_PAGINA, buscar, orden)
			.then((d) => {
				if (vigente) {
					setDatos(d);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo cargar la validación."));
			});
		return () => {
			vigente = false;
		};
	}, [estado, pagina, recarga, buscar, orden]);

	const tipo = datos?.tipo ?? null;
	const pestanas: { valor: FiltroValidacion; texto: string }[] =
		tipo === "costero"
			? [
					{ valor: "por_validar", texto: "Sin revisar" },
					{ valor: "validadas", texto: "Del tema" },
					{ valor: "en_conversacion", texto: "No son del tema" },
					{ valor: "todas", texto: "Todas" },
				]
			: [
					{ valor: "por_validar", texto: "Por validar" },
					{ valor: "en_conversacion", texto: "En conversación" },
					{ valor: "validadas", texto: "Validadas" },
					{ valor: "todas", texto: "Todas" },
				];

	function recargar() {
		setRecarga((n) => n + 1);
	}

	// J6-A1: el resultado queda junto a los botones del lote y, como la lista se
	// recarga, también en el aviso fijo de abajo.
	async function lote() {
		await accLote.correr(
			async () => {
				const r = await deAcuerdoEnLote([...elegidas]);
				setElegidas(new Set());
				setConfirmar(false);
				recargar();
				return `Listo: de acuerdo con ${cuantas(r.validadas, "evaluación", "evaluaciones")}.`;
			},
			{ error: "No se pudieron validar.", lejos: true },
		);
	}

	const ultima = Math.max(1, Math.ceil((datos?.total ?? 0) / POR_PAGINA));
	const descripcion =
		tipo === "juridico"
			? `Evaluaciones de los semilleristas de ${datos?.sede ?? "su sede"}. Revise si cada calificación tiene sentido o si fue muy generosa o muy corta. Si no está de acuerdo, explique por qué: quien calificó le responde y puede corregir.`
			: tipo === "costero"
				? "Revise si cada pregunta es del tema de playas y gestión costera. Las que no lo son no cuentan para premios."
				: "Vista de todas las evaluaciones y su validación (solo lectura).";

	return (
		<div className="pnl-pag">
			<title>Validar evaluaciones: evaluación de ATLAS</title>
			<EncabezadoEvaluacion />
			<CabezaPestana titulo="Validar evaluaciones">{descripcion}</CabezaPestana>

			<section className="pnl-bloque" aria-labelledby="t-val">
				<h2 id="t-val" className="sr">
					Evaluaciones
				</h2>
				<div className="pnl-controles pnl-mb">
						<div className="pnl-campo">
							<label htmlFor="b-buscar">Buscar</label>
							<input
								id="b-buscar"
								type="search"
								placeholder="Ej.: 486, P081 o kiosco"
								className="pnl-input pnl-input-ancho"
								value={borrador}
								onChange={(e) => setBorrador(e.target.value)}
								onBlur={() => {
									setBuscar(borrador);
									setPagina(1);
								}}
								onKeyDown={(e) => {
									if (e.key === "Enter") {
										setBuscar(borrador);
										setPagina(1);
									}
								}}
							/>
						</div>
						<div className="pnl-campo">
							<label htmlFor="b-orden">Orden</label>
							<select
								id="b-orden"
								value={orden}
								onChange={(e) => {
									setOrden(e.target.value as "antiguas" | "recientes");
									setPagina(1);
								}}
							>
								<option value="antiguas">Más antiguas primero</option>
								<option value="recientes">Más recientes primero</option>
							</select>
						</div>
						<LimpiarFiltros
							activo={!!(buscar || borrador)}
							onLimpiar={() => {
								setBorrador("");
								setBuscar("");
								setPagina(1);
							}}
						/>
				</div>
				<div className="pnl-pestanas" role="group" aria-label="Mostrar">
					{pestanas.map((p) => (
						<button
							key={p.valor}
							type="button"
							aria-pressed={estado === p.valor}
							onClick={() => {
								setEstado(p.valor);
								setPagina(1);
								setElegidas(new Set());
							}}
						>
							{p.texto}
							{datos ? <span className="pnl-pestana-n num">{numero(datos.conteos[p.valor] ?? 0)}</span> : null}
						</button>
					))}
				</div>

				<AparecerSi valor={error}>
					{(error) => (
						<div className="pnl-error" role="alert">
							<IconoAviso />
							<div>
								<b>Algo salió mal.</b>
								<p>{error}</p>
							</div>
						</div>
					)}
				</AparecerSi>

				{tipo === "juridico" && estado === "por_validar" && datos?.items.length ? (
					<div className="pnl-lote">
						<Aparece abierto={confirmar} enfocar>
							<div className="pnl-confirmar" role="group" aria-labelledby="t-lote">
								<p id="t-lote">
									¿Marcar “De acuerdo” en {elegidas.size === 1 ? "la evaluación seleccionada" : `las ${numero(elegidas.size)} evaluaciones seleccionadas`}? Quedan
									validadas con su nombre y la fecha de hoy.
								</p>
								<div className="pnl-acciones">
									<button type="button" className="pnl-btn" onClick={lote}>
										Sí, de acuerdo con {numero(elegidas.size)}
									</button>
									<button type="button" className="pnl-btn-sec" data-foco onClick={() => setConfirmar(false)}>
										Cancelar
									</button>
								</div>
							</div>
						</Aparece>
						{confirmar ? null : (
							<div className="pnl-acciones">
								{/* J6-A9: toda acción tiene su contraria a la vista. */}
								{elegidas.size ? (
									<button type="button" className="pnl-btn-sec" onClick={() => setElegidas(new Set())}>
										Quitar la selección ({numero(elegidas.size)})
									</button>
								) : (
									<button
										type="button"
										className="pnl-btn-sec"
										onClick={() =>
											setElegidas(
												new Set(
													datos.items.flatMap((i) =>
														i.evaluaciones.filter((e) => e.estado === "por_validar").map((e) => e.id),
													),
												),
											)
										}
									>
										Seleccionar las {numero(datos.items.length)} de esta página
									</button>
								)}
								{/* PQ-109: sin selección no se ofrece la acción en lote. */}
								{elegidas.size ? (
									<button type="button" className="pnl-btn" onClick={() => setConfirmar(true)}>
										De acuerdo con las seleccionadas ({numero(elegidas.size)})
									</button>
								) : null}
							</div>
						)}
						<ResultadoJunto resultado={accLote.resultado} />
					</div>
				) : null}

				{!datos && !error ? <p className="pnl-cargando">Cargando…</p> : null}
				{datos && datos.items.length === 0 ? <p className="pnl-vacio">No hay nada en esta lista.</p> : null}
				{datos?.items.length ? (
					<ol className="pnl-filas" aria-label="Preguntas">
						{datos.items.map((it) => (
							<FilaValidacion
								key={it.message_id}
								item={it}
								tipo={tipo}
								elegidas={elegidas}
								onElegir={(id, si) =>
									setElegidas((prev) => {
										const n = new Set(prev);
										if (si) n.add(id);
										else n.delete(id);
										return n;
									})
								}
								onCambio={recargar}
							/>
						))}
					</ol>
				) : null}
				{datos && datos.total > POR_PAGINA ? (
					<nav className="pnl-pagin" aria-label="Páginas">
						<span>
							Página {numero(pagina)} de {numero(ultima)}
						</span>
						<div>
							<button type="button" className="pnl-btn-sec" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
								Anteriores
							</button>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={pagina >= ultima}
								onClick={() => setPagina(pagina + 1)}
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

function FilaValidacion({
	item,
	tipo,
	elegidas,
	onElegir,
	onCambio,
}: {
	item: ItemValidacion;
	tipo: "juridico" | "costero" | null;
	elegidas: Set<string>;
	onElegir: (id: string, si: boolean) => void;
	onCambio: () => void;
}) {
	return (
		<li className="pnl-fila pnl-fila-val">
			<div className="pnl-fila-q">
				<p className="pnl-fila-titulo" style={{ margin: 0 }}>
					<span className="pnl-num-preg">Pregunta {item.numero}</span>
				</p>
				<p className="pnl-pregunta-texto">{item.pregunta}</p>
				<p className="pnl-fila-meta">
					<span className="pnl-etq">{item.codigo}</span>
					<span>{item.tipo_playa_nombre ?? "Sin tipo"}</span>
					<span>{diaMesCalendario(item.fecha)}</span>
					{item.pertinente === false ? (
						<ChipEstado tono="ojo">No es del tema (gestión costera)</ChipEstado>
					) : null}
				</p>
				{tipo === "costero" ? (
					<Pertinencia item={item} onCambio={onCambio} />
				) : (
					item.evaluaciones.map((e) => (
						<Evaluacion
							key={e.id}
							e={e}
							puedeValidar={tipo === "juridico"}
							elegida={elegidas.has(e.id)}
							onElegir={(si) => onElegir(e.id, si)}
							onCambio={onCambio}
						/>
					))
				)}
			</div>
		</li>
	);
}

function Evaluacion({
	e,
	puedeValidar,
	elegida,
	onElegir,
	onCambio,
}: {
	e: EvaluacionV;
	puedeValidar: boolean;
	elegida: boolean;
	onElegir: (si: boolean) => void;
	onCambio: () => void;
}) {
	const [abierta, setAbierta] = useState(false);
	const [detalle, setDetalle] = useState<DetalleEvaluacion | null>(null);
	const [modo, setModo] = useState<"nada" | "desacuerdo">("nada");
	const [comentario, setComentario] = useState("");
	const [error, setError] = useState<string | null>(null);
	const acc = useAccion();
	const id = e.id.slice(0, 8);

	async function abrir() {
		const nuevo = !abierta;
		setAbierta(nuevo);
		if (nuevo && !detalle) {
			try {
				setDetalle(await pedirDetalle(e.id));
			} catch (err) {
				setError(mensajeError(err, "No se pudo abrir la conversación."));
			}
		}
	}

	async function validar(deAcuerdo: boolean) {
		await acc.correr(
			async () => {
				await validarEvaluacion(e.id, deAcuerdo, comentario.trim() || undefined);
				setModo("nada");
				setComentario("");
				onCambio();
				return deAcuerdo
					? `Guardado: de acuerdo con la evaluación de ${e.evaluador}.`
					: `Enviado a ${e.evaluador}: no está de acuerdo.`;
			},
			{ lejos: true },
		);
	}

	return (
		<div className="pnl-eval-val">
			<div className="pnl-eval-cab">
				{puedeValidar && e.estado === "por_validar" ? (
					<label className="pnl-elegir">
						<input type="checkbox" checked={elegida} onChange={(ev) => onElegir(ev.target.checked)} />
						<span className="sr">Seleccionar la evaluación de {e.evaluador}</span>
					</label>
				) : null}
				<p>
					<b>{e.evaluador}</b> ({e.sede}): <ChipNivel ct={e.ct} texto={NIVELES[e.ct]} /> forma {e.forma} (F {e.f1}-{e.f2}-{e.f3}), valor de fondo {e.cv} (Cv),
					total {e.total}
					{e.valida ? "" : ", marcada no válida"}
				</p>
				<span className={`pnl-estado ${e.estado === "validada" ? "bien" : e.estado === "en_conversacion" ? "ojo" : "espera"}`}>
					{TEXTO_VALIDACION[e.estado]}
				</span>
			</div>
			{e.observaciones ? <p className="pnl-esperaba">Observaciones: “{e.observaciones}”</p> : null}
			<AparecerSi valor={error}>
				{(error) => (
					<p className="pnl-error-linea" role="alert">
						{error}
					</p>
				)}
			</AparecerSi>
			<Aparece abierto={puedeValidar && modo === "desacuerdo"} enfocar>
				<div className="pnl-campo pnl-mt">
					{e.estado === "validada" ? (
						<p className="pnl-nota" style={{ marginTop: 0 }}>
							Hoy está validada. Si cambia a “No de acuerdo”, vuelve a la conversación con {e.evaluador} y el cambio
							queda en el historial.
						</p>
					) : null}
					<label htmlFor={`d-${id}`}>¿Por qué no está de acuerdo? (lo verá {e.evaluador})</label>
					<textarea id={`d-${id}`} value={comentario} maxLength={2000} onChange={(ev) => setComentario(ev.target.value)} />
					<div className="pnl-acciones">
						<button type="button" className="pnl-btn" disabled={!comentario.trim()} onClick={() => validar(false)}>
							Enviar “No de acuerdo”
						</button>
						<button type="button" className="pnl-btn-sec" onClick={() => setModo("nada")}>
							Cancelar
						</button>
					</div>
				</div>
			</Aparece>
			<div className="pnl-acciones">
				{puedeValidar && e.estado !== "validada" && modo === "nada" ? (
					<>
						<button type="button" className="pnl-btn-sec" disabled={acc.enviando} onClick={() => validar(true)}>
							De acuerdo<span className="sr"> con la evaluación de {e.evaluador}</span>
						</button>
						<button type="button" className="pnl-btn-sec" onClick={() => setModo("desacuerdo")}>
							No de acuerdo<span className="sr"> con la evaluación de {e.evaluador}</span>
						</button>
					</>
				) : null}
				{/* PQ-107: un "De acuerdo" ya dado se puede cambiar (queda en el historial). */}
				{puedeValidar && e.estado === "validada" && modo === "nada" ? (
					<button type="button" className="pnl-btn-sec" onClick={() => setModo("desacuerdo")}>
						Cambiar a “No de acuerdo”<span className="sr"> en la evaluación de {e.evaluador}</span>
					</button>
				) : null}
				<button type="button" className="pnl-enlace" aria-expanded={abierta} onClick={abrir}>
					{abierta
						? e.comentarios
							? "Ocultar conversación"
							: "Cerrar"
						: e.comentarios
							? `Ver conversación (${e.comentarios})`
							: `Escribirle a ${e.evaluador}`}
				</button>
			</div>
			<ResultadoJunto resultado={acc.resultado} />
			<Aparece abierto={abierta && detalle !== null}>
				{detalle ? <Hilo detalle={detalle} onCambio={setDetalle} lado="validacion" /> : null}
			</Aparece>
		</div>
	);
}

function Pertinencia({ item, onCambio }: { item: ItemValidacion; onCambio: () => void }) {
	const [comentario, setComentario] = useState("");
	const acc = useAccion();
	const id = item.message_id.slice(0, 8);

	async function marcar(pertinente: boolean) {
		await acc.correr(
			async () => {
				await marcarPertinencia(item.message_id, pertinente, comentario.trim() || undefined);
				onCambio();
				return `Pregunta ${item.numero}: ${pertinente ? "marcada como del tema" : "marcada como fuera del tema"}.`;
			},
			{ lejos: true },
		);
	}

	return (
		<div className="pnl-eval-val">
			<p>
				{item.pertinente === null ? (
					<ChipEstado tono="sin">Sin revisar</ChipEstado>
				) : item.pertinente ? (
					<ChipEstado tono="bien">Del tema</ChipEstado>
				) : (
					<ChipEstado tono="ojo">Fuera del tema: no cuenta para premios</ChipEstado>
				)}
			</p>
			<div className="pnl-campo">
				<label htmlFor={`p-${id}`}>Comentario (opcional)</label>
				<textarea id={`p-${id}`} value={comentario} maxLength={2000} onChange={(e) => setComentario(e.target.value)} />
			</div>
			<div className="pnl-acciones">
				<button type="button" className="pnl-btn-sec" onClick={() => marcar(true)} aria-pressed={item.pertinente === true}>
					Es del tema<span className="sr">: pregunta {item.numero}</span>
				</button>
				<button type="button" className="pnl-btn-sec" onClick={() => marcar(false)} aria-pressed={item.pertinente === false}>
					No es del tema<span className="sr">: pregunta {item.numero}</span>
				</button>
			</div>
			<ResultadoJunto resultado={acc.resultado} />
		</div>
	);
}

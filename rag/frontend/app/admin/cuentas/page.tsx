"use client";

import { useEffect, useState } from "react";
import { cuantas, fechaHora, mensajeError, numero } from "@/lib/admin/panel";
import { reasignarPendientes } from "@/lib/admin/evaluacion";
import {
	ROLES,
	SEDES,
	TIPOS_PLAYA,
	cambiarCuenta,
	crearLote,
	csvALista,
	detalleAuditoria,
	leerLista,
	listarCuentas,
	nombreTipo,
	nuevaClave,
	pedirAuditoria,
	textoRol,
	type Credencial,
	type EntradaAuditoria,
	type Cuenta,
	type Rol,
	type Sede,
} from "@/lib/admin/cuentas";
import { IconoAviso } from "@/components/admin/panel/Estados";

/**
 * Cuentas del ejercicio de validación (documento del profe): cada
 * participante con su número y un solo tipo de usuario de playa; evaluadores
 * con su sede; comité. Se crean por lote y las claves se muestran una sola
 * vez para imprimirlas y entregarlas.
 */
export default function PaginaCuentas() {
	const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);
	const [filtroRol, setFiltroRol] = useState<string>("");
	const [filtroTipo, setFiltroTipo] = useState<string>("");
	// PQ-53: buscar por número, nombre o correo.
	const [buscar, setBuscar] = useState("");
	const [credenciales, setCredenciales] = useState<Credencial[]>([]);
	const [pagina, setPagina] = useState(1);

	useEffect(() => {
		let vigente = true;
		listarCuentas()
			.then((r) => {
				if (vigente) {
					setCuentas(r.items);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las cuentas."));
			});
		return () => {
			vigente = false;
		};
	}, [intento]);

	const visibles = (cuentas ?? []).filter(
		(c) =>
			c.correo !== "demo-seed@atlas.local" &&
			(!filtroRol || c.rol === filtroRol || (filtroRol === "admin" && c.rol === "super-admin")) &&
			(!filtroTipo || c.tipo_playa === Number(filtroTipo)) &&
			(!buscar.trim() ||
				[c.codigo, c.nombre, c.correo].some((v) =>
					(v ?? "").toLowerCase().includes(buscar.trim().toLowerCase()),
				)),
	);
	// 20 por página: con 80 participantes la lista entera era muy larga (PQ-45).
	const POR_PAGINA = 20;
	const ultimaPagina = Math.max(1, Math.ceil(visibles.length / POR_PAGINA));
	const paginaActual = Math.min(pagina, ultimaPagina);
	const enPagina = visibles.slice((paginaActual - 1) * POR_PAGINA, paginaActual * POR_PAGINA);

	return (
		<div className="pnl-pag">
			<title>Cuentas del ejercicio: panel de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Cuentas del ejercicio</h1>
					<p className="pnl-sub">
						Participantes con su número y tipo de usuario de playa, evaluadores con su sede y comité.
					</p>
				</div>
			</div>

			<CrearCuentas
				onCreadas={(c) => {
					setCredenciales(c);
					setIntento((n) => n + 1);
				}}
			/>

			{credenciales.length ? (
				<Credenciales lista={credenciales} onCerrar={() => setCredenciales([])} />
			) : null}

			<section className="pnl-bloque pnl-no-imprimir" aria-labelledby="t-cuentas">
				<div className="pnl-bloque-cab">
					<div>
						<h2 id="t-cuentas">Cuentas</h2>
						<p>{cuentas ? `${numero(visibles.length)} con este filtro` : " "}</p>
					</div>
					<div className="pnl-controles">
						<div className="pnl-campo">
							<label htmlFor="f-buscar">Buscar</label>
							<input
								id="f-buscar"
								type="search"
								placeholder="Ej.: P007, Ana o correo"
								className="pnl-input pnl-input-ancho"
								value={buscar}
								onChange={(e) => {
									setBuscar(e.target.value);
									setPagina(1);
								}}
							/>
						</div>
						<div className="pnl-campo">
							<label htmlFor="f-rol">Rol</label>
							<select id="f-rol" value={filtroRol} onChange={(e) => {
									setFiltroRol(e.target.value);
									setPagina(1);
								}}>
								<option value="">Todos</option>
								{ROLES.map((r) => (
									<option key={r.valor} value={r.valor}>
										{r.texto}
									</option>
								))}
							</select>
						</div>
						<div className="pnl-campo">
							<label htmlFor="f-tipo">Tipo de usuario de playa</label>
							<select id="f-tipo" value={filtroTipo} onChange={(e) => {
									setFiltroTipo(e.target.value);
									setPagina(1);
								}}>
								<option value="">Todos</option>
								{TIPOS_PLAYA.map((t) => (
									<option key={t.id} value={t.id}>
										{t.id}. {t.nombre}
									</option>
								))}
							</select>
						</div>
					</div>
				</div>

				{error ? (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudieron cargar las cuentas.</b>
							<p>{error}</p>
							<button type="button" className="pnl-btn-sec" onClick={() => setIntento((n) => n + 1)}>
								Intentar otra vez
							</button>
						</div>
					</div>
				) : null}
				{!cuentas && !error ? <p className="pnl-cargando">Cargando cuentas…</p> : null}
				{cuentas && visibles.length === 0 ? (
					<p className="pnl-vacio">
						<b>No hay cuentas con este filtro.</b>
						Pruebe con “Todos” o cree cuentas arriba.
					</p>
				) : null}
				{visibles.length ? (
					<ol className="pnl-filas" aria-label="Cuentas">
						{enPagina.map((c) => (
							<FilaCuenta
								key={c.uid}
								cuenta={c}
								onCambiada={(nueva) =>
									setCuentas((prev) => (prev ?? []).map((x) => (x.uid === nueva.uid ? nueva : x)))
								}
							/>
						))}
					</ol>
				) : null}
				{visibles.length > POR_PAGINA ? (
					<nav className="pnl-pagin" aria-label="Páginas de cuentas">
						<span>
							{numero((paginaActual - 1) * POR_PAGINA + 1)} a{" "}
							{numero(Math.min(paginaActual * POR_PAGINA, visibles.length))} de {numero(visibles.length)}{" "}
							cuentas
						</span>
						<div>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={paginaActual <= 1}
								onClick={() => setPagina(paginaActual - 1)}
							>
								Anteriores
							</button>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={paginaActual >= ultimaPagina}
								onClick={() => setPagina(paginaActual + 1)}
							>
								Siguientes
							</button>
						</div>
					</nav>
				) : null}
			</section>
			<Historial />
		</div>
	);
}

/** CHECKLIST-FINAL c7: quién creó cuentas, cambió roles, generó claves o validó en lote. */
function Historial() {
	const [abierto, setAbierto] = useState(false);
	const [datos, setDatos] = useState<{ items: EntradaAuditoria[]; total: number } | null>(null);
	const [error, setError] = useState<string | null>(null);

	async function abrir() {
		const nuevo = !abierto;
		setAbierto(nuevo);
		if (!nuevo) return;
		setError(null);
		try {
			setDatos(await pedirAuditoria(100));
		} catch (e) {
			setError(mensajeError(e, "No se pudo cargar el historial."));
		}
	}

	return (
		<section className="pnl-bloque pnl-no-imprimir" aria-labelledby="t-historial">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-historial">Historial de cambios</h2>
					<p>Quién creó cuentas, cambió datos, generó claves, desactivó cuentas o validó calificaciones.</p>
				</div>
				<button type="button" className="pnl-btn-sec" onClick={abrir} aria-expanded={abierto}>
					{abierto ? "Ocultar" : "Ver historial"}
				</button>
			</div>
			{abierto && error ? (
				<p className="pnl-error-linea" role="alert">
					{error}
				</p>
			) : null}
			{abierto && !datos && !error ? <p className="pnl-cargando">Cargando historial…</p> : null}
			{abierto && datos && datos.items.length === 0 ? (
				<p className="pnl-vacio">Todavía no hay cambios registrados.</p>
			) : null}
			{abierto && datos && datos.items.length ? (
				<div className="pnl-tabla-datos" role="region" aria-label="Historial de cambios" tabIndex={0}>
					<table>
						<thead>
							<tr>
								<th scope="col">Fecha</th>
								<th scope="col">Quién</th>
								<th scope="col">Qué hizo</th>
								<th scope="col">A quién</th>
								<th scope="col">Detalle</th>
							</tr>
						</thead>
						<tbody>
							{datos.items.map((e, i) => (
								<tr key={`${e.fecha}-${i}`}>
									<td>{fechaHora(e.fecha)}</td>
									<td>{e.quien}</td>
									<td>{e.texto}</td>
									<td>{e.objetivo ?? "—"}</td>
									<td>{detalleAuditoria(e) || "—"}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			) : null}
		</section>
	);
}

function CrearCuentas({ onCreadas }: { onCreadas: (c: Credencial[]) => void }) {
	const [rol, setRol] = useState<Rol>("user");
	const [sede, setSede] = useState<Sede>("Santa Marta");
	const [texto, setTexto] = useState("");
	const [importado, setImportado] = useState<string | null>(null);
	const [errores, setErrores] = useState<string[]>([]);
	const [enviando, setEnviando] = useState(false);

	async function crear(e: React.FormEvent) {
		e.preventDefault();
		const { personas, errores: malos } = leerLista(texto, rol, sede);
		if (malos.length || !personas.length) {
			setErrores(malos.length ? malos : ["Escriba al menos una persona."]);
			return;
		}
		setErrores([]);
		setEnviando(true);
		try {
			const r = await crearLote(personas);
			setTexto("");
			onCreadas(r.creadas);
		} catch (err) {
			setErrores([mensajeError(err, "No se pudieron crear las cuentas.")]);
		} finally {
			setEnviando(false);
		}
	}

	return (
		<section className="pnl-bloque pnl-no-imprimir" aria-labelledby="t-crear">
			<h2 id="t-crear">Crear cuentas</h2>
			<p className="pnl-sub" style={{ marginBottom: 14 }}>
				Una persona por renglón. Para participantes escriba “Nombre; tipo; organización” (el tipo es un número
				del 1 al 5 o su nombre; la organización, institución o asociación es opcional). El número de
				participante (P001, P002…) se asigna solo.
			</p>
			<ul className="pnl-tipos">
				{TIPOS_PLAYA.map((t) => (
					<li key={t.id}>
						<b>{t.id}.</b> {t.largo}
					</li>
				))}
			</ul>
			<form onSubmit={crear} className="pnl-form">
				<div className="pnl-controles">
					<div className="pnl-campo">
						<label htmlFor="c-rol">Crear como</label>
						<select id="c-rol" value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
							{ROLES.map((r) => (
								<option key={r.valor} value={r.valor}>
									{r.texto}
								</option>
							))}
						</select>
					</div>
					{rol === "evaluador" ? (
						<div className="pnl-campo">
							<label htmlFor="c-sede">Sede</label>
							<select id="c-sede" value={sede} onChange={(e) => setSede(e.target.value as Sede)}>
								{SEDES.map((s) => (
									<option key={s}>{s}</option>
								))}
							</select>
						</div>
					) : null}
				</div>
				{rol === "user" ? (
					<div className="pnl-campo" style={{ marginTop: 14 }}>
						<label htmlFor="c-csv">Importar la lista de inscritos (CSV exportado de Forms)</label>
						<input
							id="c-csv"
							type="file"
							accept=".csv,text/csv"
							onChange={async (e) => {
								const archivo = e.target.files?.[0];
								if (!archivo) return;
								const r = csvALista(await archivo.text());
								setImportado(
									r.faltan.length
										? r.faltan.join(" ")
										: `Se leyeron ${r.filas} inscritos. Revise la lista abajo y luego toque “Crear cuentas”.`,
								);
								if (r.lista) setTexto(r.lista);
								e.target.value = "";
							}}
						/>
						{importado ? (
							<p className="pnl-sub" role="status">
								{importado}
							</p>
						) : null}
					</div>
				) : null}
				<div className="pnl-campo" style={{ marginTop: 14 }}>
					<label htmlFor="c-lista">{rol === "user" ? "Nombre; tipo; organización" : "Nombres"}</label>
					<textarea
						id="c-lista"
						className="pnl-textarea"
						rows={5}
						value={texto}
						onChange={(e) => setTexto(e.target.value)}
						placeholder={
							rol === "user"
								? "María Pérez; 2; Asociación de pescadores de Taganga\nJuan Ríos; Turistas"
								: "Ana Gómez\nLuis Díaz"
						}
						aria-describedby={errores.length ? "c-errores" : undefined}
					/>
				</div>
				{errores.length ? (
					<div id="c-errores" className="pnl-error" role="alert" style={{ marginTop: 12 }}>
						<IconoAviso />
						<div>
							<b>Revise la lista.</b>
							<ul style={{ margin: 0, paddingLeft: 20 }}>
								{errores.map((e) => (
									<li key={e}>{e}</li>
								))}
							</ul>
						</div>
					</div>
				) : null}
				<p style={{ marginTop: 14 }}>
					<button type="submit" className="pnl-btn" disabled={enviando}>
						{enviando ? "Creando…" : "Crear cuentas"}
					</button>
				</p>
			</form>
		</section>
	);
}

function Credenciales({ lista, onCerrar }: { lista: Credencial[]; onCerrar: () => void }) {
	// Dirección pública de ATLAS (la misma del panel, sin /admin).
	const direccionAtlas = typeof window === "undefined" ? "" : window.location.host;
	return (
		<section className="pnl-bloque pnl-credenciales" aria-labelledby="t-cred">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-cred">Credenciales para entregar</h2>
					<p>Las claves solo se muestran ahora. Imprímalas o cópielas antes de cerrar.</p>
				</div>
				<div className="pnl-controles pnl-no-imprimir">
					<button type="button" className="pnl-btn" onClick={() => window.print()}>
						Imprimir credenciales
					</button>
					<button type="button" className="pnl-btn-sec" onClick={onCerrar}>
						Ya las guardé
					</button>
				</div>
			</div>
			<ol className="pnl-tarjetas-cred">
				{lista.map((c) => (
					<li key={c.uid}>
						<p className="pnl-cred-nombre">
							{c.codigo ? <span className="pnl-etq">{c.codigo}</span> : null}
							{c.nombre}
						</p>
						<p>
							{textoRol(c.rol)}
							{c.tipo_playa ? `: ${nombreTipo(c.tipo_playa)}` : ""}
							{c.sede ? `: ${c.sede}` : ""}
						</p>
						<dl>
							<div>
								<dt>Correo</dt>
								<dd>{c.correo}</dd>
							</div>
							<div>
								<dt>Clave</dt>
								<dd className="pnl-clave">{c.clave}</dd>
							</div>
						</dl>
						{/* PQ-51: la tarjeta dice dónde entrar y qué hacer. */}
						<p className="pnl-cred-como">
							Entre en <b>{direccionAtlas}</b>, escriba este correo y esta clave, y toque “Entrar”.
						</p>
					</li>
				))}
			</ol>
		</section>
	);
}

function FilaCuenta({ cuenta, onCambiada }: { cuenta: Cuenta; onCambiada: (c: Cuenta) => void }) {
	const [editando, setEditando] = useState(false);
	const [rol, setRol] = useState<Rol>((cuenta.rol === "super-admin" ? "admin" : cuenta.rol) as Rol);
	const [tipo, setTipo] = useState<number>(cuenta.tipo_playa ?? 1);
	const [sede, setSede] = useState<Sede>((cuenta.sede as Sede) ?? "Santa Marta");
	const [validacion, setValidacion] = useState<"juridico" | "costero" | "ninguna">(cuenta.validacion ?? "ninguna");
	const pideSede = rol === "evaluador" || (rol === "comite" && validacion === "juridico");
	const [practica, setPractica] = useState(cuenta.practica ?? false);
	const [clave, setClave] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [confirmarBaja, setConfirmarBaja] = useState(false);
	const [confirmarReasignar, setConfirmarReasignar] = useState(false);
	const [aviso, setAviso] = useState<string | null>(null);

	// E1: sus preguntas sin evaluar pasan a otro semillerista de su sede.
	async function reasignar() {
		setError(null);
		try {
			const r = await reasignarPendientes(cuenta.uid);
			setAviso(
				r.reasignadas
					? `${cuantas(r.reasignadas, "pregunta pasó", "preguntas pasaron")} a otro semillerista de su sede.`
					: "No tenía preguntas pendientes.",
			);
			setConfirmarReasignar(false);
		} catch (e) {
			setError(mensajeError(e, "No se pudo reasignar."));
		}
	}
	const activa = cuenta.activa !== false;
	const id = cuenta.uid.slice(0, 8);

	// CHECKLIST-FINAL c2: desactivar sin borrar el historial (y reactivar).
	async function cambiarActiva(nueva: boolean) {
		setError(null);
		try {
			onCambiada(await cambiarCuenta(cuenta.uid, { activa: nueva }));
			setConfirmarBaja(false);
		} catch (e) {
			setError(mensajeError(e, "No se pudo cambiar la cuenta."));
		}
	}

	async function guardar() {
		setError(null);
		try {
			const nueva = await cambiarCuenta(cuenta.uid, {
				rol,
				...(rol === "user" ? { tipo_playa: tipo } : {}),
				...(pideSede ? { sede } : {}),
				...(rol === "comite" ? { validacion } : {}),
				practica,
			});
			onCambiada(nueva);
			setEditando(false);
		} catch (e) {
			setError(mensajeError(e, "No se pudo guardar."));
		}
	}

	async function restablecer() {
		setError(null);
		try {
			setClave((await nuevaClave(cuenta.uid)).clave);
		} catch (e) {
			setError(mensajeError(e, "No se pudo generar la clave."));
		}
	}

	return (
		<li className={activa ? "pnl-fila" : "pnl-fila pnl-fila-inactiva"}>
			<div className="pnl-fila-q">
				<p className="pnl-fila-titulo" style={{ margin: 0 }}>
					{cuenta.codigo ? <span className="pnl-etq">{cuenta.codigo}</span> : null}
					{cuenta.nombre || "Sin nombre"}
					{activa ? null : <span className="pnl-inactiva">, desactivada</span>}
					{cuenta.practica ? <span className="pnl-practica">Práctica</span> : null}
				</p>
				<p className="pnl-fila-meta">
					<span>{textoRol(cuenta.rol)}</span>
					{cuenta.tipo_playa ? <span>Tipo: {nombreTipo(cuenta.tipo_playa)}</span> : null}
					{cuenta.sede ? <span>Sede: {cuenta.sede}</span> : null}
					{cuenta.validacion ? (
						<span>Valida: {cuenta.validacion === "juridico" ? "lo jurídico de su sede" : "gestión costera"}</span>
					) : null}
					{cuenta.organizacion ? <span>Organización: {cuenta.organizacion}</span> : null}
					<span>{cuenta.correo}</span>
				</p>
				{clave ? (
					<p className="pnl-esperaba" role="status">
						Clave nueva: <b className="pnl-clave">{clave}</b> (solo se muestra ahora)
					</p>
				) : null}
				{error ? (
					<p className="pnl-error-linea" role="alert">
						{error}
					</p>
				) : null}
				{aviso ? (
					<p className="pnl-ok" role="status">
						{aviso}
					</p>
				) : null}
				{confirmarReasignar ? (
					<div className="pnl-confirmar" role="group" aria-labelledby={`re-${id}`}>
						<p id={`re-${id}`}>
							¿Pasar las preguntas sin evaluar de {cuenta.nombre || cuenta.correo} a los demás semilleristas de{" "}
							{cuenta.sede ?? "su sede"}? Lo que ya evaluó se queda con su nombre.
						</p>
						<div className="pnl-acciones">
							<button type="button" className="pnl-btn" onClick={reasignar}>
								Sí, reasignar
							</button>
							<button type="button" className="pnl-btn-sec" onClick={() => setConfirmarReasignar(false)}>
								Cancelar
							</button>
						</div>
					</div>
				) : null}
				{confirmarBaja ? (
					<div className="pnl-confirmar" role="group" aria-labelledby={`baja-${id}`}>
						<p id={`baja-${id}`}>
							¿Desactivar la cuenta de {cuenta.nombre || cuenta.correo}? No podrá entrar a ATLAS; sus preguntas y
							calificaciones se conservan y se puede reactivar.
							{cuenta.rol === "evaluador" ? " Las preguntas que tenía sin evaluar pasan a otro semillerista de su sede." : ""}
						</p>
						<div className="pnl-acciones">
							<button type="button" className="pnl-btn" onClick={() => cambiarActiva(false)}>
								Sí, desactivar
							</button>
							<button type="button" className="pnl-btn-sec" onClick={() => setConfirmarBaja(false)}>
								Cancelar
							</button>
						</div>
					</div>
				) : null}
				{editando ? (
					<div className="pnl-controles" style={{ marginTop: 10 }}>
						<div className="pnl-campo">
							<label htmlFor={`r-${id}`}>Rol</label>
							<select id={`r-${id}`} value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
								{ROLES.map((r) => (
									<option key={r.valor} value={r.valor}>
										{r.texto}
									</option>
								))}
							</select>
						</div>
						{rol === "user" ? (
							<div className="pnl-campo">
								<label htmlFor={`t-${id}`}>Tipo de usuario de playa</label>
								<select id={`t-${id}`} value={tipo} onChange={(e) => setTipo(Number(e.target.value))}>
									{TIPOS_PLAYA.map((t) => (
										<option key={t.id} value={t.id}>
											{t.id}. {t.nombre}
										</option>
									))}
								</select>
							</div>
						) : null}
						{rol === "comite" ? (
							<div className="pnl-campo">
								<label htmlFor={`v-${id}`}>Qué valida</label>
								<select
									id={`v-${id}`}
									value={validacion}
									onChange={(e) => setValidacion(e.target.value as "juridico" | "costero" | "ninguna")}
								>
									<option value="ninguna">Nada (solo comité)</option>
									<option value="juridico">Lo jurídico de su sede</option>
									<option value="costero">Gestión costera (pertinencia)</option>
								</select>
							</div>
						) : null}
						{pideSede ? (
							<div className="pnl-campo">
								<label htmlFor={`s-${id}`}>Sede</label>
								<select id={`s-${id}`} value={sede} onChange={(e) => setSede(e.target.value as Sede)}>
									{SEDES.map((s) => (
										<option key={s}>{s}</option>
									))}
								</select>
							</div>
						) : null}
						<label className="pnl-check">
							<input type="checkbox" checked={practica} onChange={(e) => setPractica(e.target.checked)} />
							<span>Cuenta de práctica (no cuenta para resultados)</span>
						</label>
						<button type="button" className="pnl-btn" onClick={guardar}>
							Guardar
						</button>
						<button type="button" className="pnl-btn-sec" onClick={() => setEditando(false)}>
							Cancelar
						</button>
					</div>
				) : null}
			</div>
			<div className="pnl-fila-lado">
				<dl className="pnl-fila-estado">
					<div>
						<dt>Preguntas</dt>
						<dd className="pnl-veces">{numero(cuenta.preguntas)}</dd>
					</div>
				</dl>
				<div className="pnl-fila-acciones">
					<button
						type="button"
						className="pnl-btn-sec"
						onClick={() => setEditando((e) => !e)}
						aria-expanded={editando}
					>
						Cambiar<span className="sr"> datos de {cuenta.nombre || cuenta.correo}</span>
					</button>
					<button type="button" className="pnl-btn-sec" onClick={restablecer}>
						Nueva clave<span className="sr"> para {cuenta.nombre || cuenta.correo}</span>
					</button>
					{cuenta.rol === "evaluador" && activa ? (
						<button
							type="button"
							className="pnl-btn-sec"
							onClick={() => setConfirmarReasignar(true)}
							aria-expanded={confirmarReasignar}
						>
							Reasignar pendientes<span className="sr"> de {cuenta.nombre || cuenta.correo}</span>
						</button>
					) : null}
					{activa ? (
						<button
							type="button"
							className="pnl-btn-sec"
							onClick={() => setConfirmarBaja(true)}
							aria-expanded={confirmarBaja}
						>
							Desactivar<span className="sr"> la cuenta de {cuenta.nombre || cuenta.correo}</span>
						</button>
					) : (
						<button type="button" className="pnl-btn-sec" onClick={() => cambiarActiva(true)}>
							Reactivar<span className="sr"> la cuenta de {cuenta.nombre || cuenta.correo}</span>
						</button>
					)}
				</div>
			</div>
		</li>
	);
}

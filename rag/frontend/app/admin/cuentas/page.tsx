"use client";

import { useEffect, useState } from "react";
import { mensajeError, numero } from "@/lib/admin/panel";
import {
	ROLES,
	SEDES,
	TIPOS_PLAYA,
	cambiarCuenta,
	crearLote,
	leerLista,
	listarCuentas,
	nombreTipo,
	nuevaClave,
	textoRol,
	type Credencial,
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
	const [credenciales, setCredenciales] = useState<Credencial[]>([]);

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
			(!filtroTipo || c.tipo_playa === Number(filtroTipo)),
	);

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
							<label htmlFor="f-rol">Rol</label>
							<select id="f-rol" value={filtroRol} onChange={(e) => setFiltroRol(e.target.value)}>
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
							<select id="f-tipo" value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)}>
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
						{visibles.map((c) => (
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
			</section>
		</div>
	);
}

function CrearCuentas({ onCreadas }: { onCreadas: (c: Credencial[]) => void }) {
	const [rol, setRol] = useState<Rol>("user");
	const [sede, setSede] = useState<Sede>("Santa Marta");
	const [texto, setTexto] = useState("");
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
				Una persona por renglón. Para participantes escriba “Nombre; tipo” (el tipo es un número del 1 al 5 o
				su nombre). El número de participante (P001, P002…) se asigna solo.
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
				<div className="pnl-campo" style={{ marginTop: 14 }}>
					<label htmlFor="c-lista">{rol === "user" ? "Nombre; tipo" : "Nombres"}</label>
					<textarea
						id="c-lista"
						className="pnl-textarea"
						rows={5}
						value={texto}
						onChange={(e) => setTexto(e.target.value)}
						placeholder={rol === "user" ? "María Pérez; 2\nJuan Ríos; Turistas" : "Ana Gómez\nLuis Díaz"}
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
	const [clave, setClave] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const id = cuenta.uid.slice(0, 8);

	async function guardar() {
		setError(null);
		try {
			const nueva = await cambiarCuenta(cuenta.uid, {
				rol,
				...(rol === "user" ? { tipo_playa: tipo } : {}),
				...(rol === "evaluador" ? { sede } : {}),
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
		<li className="pnl-fila">
			<div className="pnl-fila-q">
				<p className="pnl-fila-titulo" style={{ margin: 0 }}>
					{cuenta.codigo ? <span className="pnl-etq">{cuenta.codigo}</span> : null}
					{cuenta.nombre || "Sin nombre"}
				</p>
				<p className="pnl-fila-meta">
					<span>{textoRol(cuenta.rol)}</span>
					{cuenta.tipo_playa ? <span>Tipo: {nombreTipo(cuenta.tipo_playa)}</span> : null}
					{cuenta.sede ? <span>Sede: {cuenta.sede}</span> : null}
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
						{rol === "evaluador" ? (
							<div className="pnl-campo">
								<label htmlFor={`s-${id}`}>Sede</label>
								<select id={`s-${id}`} value={sede} onChange={(e) => setSede(e.target.value as Sede)}>
									{SEDES.map((s) => (
										<option key={s}>{s}</option>
									))}
								</select>
							</div>
						) : null}
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
				</div>
			</div>
		</li>
	);
}

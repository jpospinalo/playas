"use client";

import "./panel.css";
import "./panel-legado.css";

import { useEffect, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { useTheme } from "@/components/providers/ThemeProvider";
import { rolEvalua } from "@/lib/admin/evaluacion";
import { AvisosProvider } from "@/components/admin/panel/Resultado";

// Panel de administración con el diseño B del flujo guiado: encabezado
// blanco con línea marino, navegación arriba (sin barra lateral), fuente del
// sistema y los tokens de `panel.css`. Las páginas antiguas (Conversaciones,
// Calificaciones, Usuarios) quedan dentro del mismo marco.

const ENLACES = [
	{ href: "/admin", texto: "Resumen" },
	{ href: "/admin/message-feedback", texto: "Opiniones" },
	{ href: "/admin/feedback", texto: "Encuestas" },
	{ href: "/admin/cuentas", texto: "Cuentas" },
	{ href: "/admin/evaluacion", texto: "Evaluación" },
];

// Evaluadores (semilleristas) y comité solo entran a la evaluación: el resto
// del panel lee datos de personas y es solo para administradores.
const ENLACES_EVALUACION = [{ href: "/admin/evaluacion", texto: "Evaluación" }];

function esAdministrador(rol: string | null | undefined): boolean {
	return rol === "admin" || rol === "super-admin";
}

// Título de la pestaña de las páginas viejas (las nuevas ponen el suyo): cada
// pantalla con su nombre, sin raya (PQ-21).
const TITULOS: Record<string, string> = {
	"/admin/usuarios": "Usuarios: panel de ATLAS",
};

const subscribeNoop = () => () => {};

function BotonTema() {
	const { resolvedTheme, setTheme } = useTheme();
	const montado = useSyncExternalStore(
		subscribeNoop,
		() => true,
		() => false,
	);
	if (!montado) return null;
	const oscuro = resolvedTheme === "dark";
	return (
		<button
			type="button"
			className="pnl-btn-sec pnl-tema"
			aria-pressed={oscuro}
			onClick={() => setTheme(oscuro ? "light" : "dark")}
		>
			Modo oscuro
		</button>
	);
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
	const { user, role, loading } = useAuth();
	const router = useRouter();
	const pathname = usePathname();

	const soloEvaluacion = !esAdministrador(role) && rolEvalua(role);
	const fueraDeEvaluacion = soloEvaluacion && !pathname.startsWith("/admin/evaluacion");

	useEffect(() => {
		if (!loading && !user) {
			router.replace("/");
		} else if (!loading && fueraDeEvaluacion) {
			router.replace("/admin/evaluacion");
		}
	}, [user, loading, router, fueraDeEvaluacion]);

	if (loading) {
		return (
			<div className="pnl">
				<main id="main-content" className="pnl-main pnl-pag">
					<p role="status" className="pnl-cargando">
						Verificando acceso…
					</p>
				</main>
			</div>
		);
	}

	if (!user || fueraDeEvaluacion) return null;

	if (!esAdministrador(role) && !soloEvaluacion) {
		return (
			<div className="pnl">
				<main id="main-content" className="pnl-main pnl-pag">
					<title>Acceso restringido: panel de ATLAS</title>
					<h1>Acceso restringido</h1>
					<p className="pnl-sub">
						Su cuenta no tiene permiso para ver el panel de administración. Si cree que
						debería tenerlo, pídalo al equipo de ATLAS.
					</p>
					<p>
						<Link href="/" className="pnl-btn-sec">
							Volver a ATLAS
						</Link>
					</p>
				</main>
			</div>
		);
	}

	return (
		<div className="pnl">
			<header className="pnl-cab">
				<div className="pnl-cab-in">
					<Link href="/admin" className="pnl-marca">
						{/* eslint-disable-next-line @next/next/no-img-element */}
						<img src="/brand/atlas-96.png" alt="" width={44} height={44} />
						<span>
							<b translate="no">ATLAS</b>
							<small>Panel de administración</small>
						</span>
					</Link>
					<nav className="pnl-nav-w" aria-label="Panel de administración">
						<ul className="pnl-nav">
							{(soloEvaluacion ? ENLACES_EVALUACION : ENLACES).map(({ href, texto }) => {
								const activo =
									href === "/admin"
										? pathname === "/admin" || pathname.startsWith("/admin/conversacion")
										: pathname.startsWith(href);
								return (
									<li key={href}>
										<Link href={href} aria-current={activo ? "page" : undefined}>
											{texto}
										</Link>
									</li>
								);
							})}
							{/* En celular "Volver a ATLAS" va aquí (PQ-44). */}
							<li className="pnl-solo-cel">
								<Link href="/">Volver a ATLAS</Link>
							</li>
						</ul>
					</nav>
					<div className="pnl-cab-acc">
						<BotonTema />
						<Link href="/" className="pnl-btn-sec">
							Volver a ATLAS
						</Link>
					</div>
				</div>
			</header>
			<AvisosProvider>
				<main id="main-content" className="pnl-main">
					{TITULOS[pathname] ? <title>{TITULOS[pathname]}</title> : null}
					{children}
				</main>
			</AvisosProvider>
		</div>
	);
}

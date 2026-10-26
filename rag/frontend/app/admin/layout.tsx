"use client";

import "./panel.css";

import { useEffect, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { useTheme } from "@/components/providers/ThemeProvider";

// Panel de administración con el diseño B del flujo guiado: encabezado
// blanco con línea marino, navegación arriba (sin barra lateral), fuente del
// sistema y los tokens de `panel.css`. Las páginas antiguas (Conversaciones,
// Calificaciones, Usuarios) quedan dentro del mismo marco.

const ENLACES = [
	{ href: "/admin", texto: "Resumen" },
	{ href: "/admin/message-feedback", texto: "Calificaciones" },
	{ href: "/admin/feedback", texto: "Conversaciones" },
	{ href: "/admin/usuarios", texto: "Usuarios" },
];

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

	useEffect(() => {
		if (!loading && !user) {
			router.replace("/");
		}
	}, [user, loading, router]);

	if (loading) {
		return (
			<div className="pnl">
				<main id="main-content" className="pnl-main">
					<p role="status" className="pnl-cargando">
						Verificando acceso…
					</p>
				</main>
			</div>
		);
	}

	if (!user) return null;

	if (role !== "admin" && role !== "super-admin") {
		return (
			<div className="pnl">
				<main id="main-content" className="pnl-main">
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
							{ENLACES.map(({ href, texto }) => {
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
			<main id="main-content" className="pnl-main">
				{children}
			</main>
		</div>
	);
}

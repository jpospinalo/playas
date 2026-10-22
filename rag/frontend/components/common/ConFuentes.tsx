import localFont from "next/font/local";

// Fuentes auto-hospedadas (sin llamadas de red en build/runtime).
// Mismos archivos que sirven next/font/google para Inter/Geist Mono con
// subset "latin" — Inter-Variable.woff2 extraído del paquete npm oficial
// @fontsource-variable/inter (Fontsource, licencia OFL — ver
// app/fonts/Inter-OFL-LICENSE.txt); GeistMono-Variable.woff2 extraído del
// paquete npm oficial "geist" (Vercel), ya una dependencia del proyecto
// (licencia OFL — ver app/fonts/Geist-OFL-LICENSE.txt).
//
// Solo las usan /chat, /admin y /about. La portada (flujo guiado) va con la
// fuente del sistema y no debe descargarlas (QA-20): por eso no están en el
// layout raíz, y next/font las limita a las rutas que montan <ConFuentes>.
const inter = localFont({
	src: "../../app/fonts/Inter-Variable.woff2",
	variable: "--font-sans",
	weight: "100 900",
	display: "swap",
});

const geistMono = localFont({
	src: "../../app/fonts/GeistMono-Variable.woff2",
	variable: "--font-mono",
	weight: "100 900",
	display: "swap",
});

/**
 * Define las variables `--font-sans` / `--font-mono` y aplica Inter a todo lo
 * que envuelve. `display: contents`: no agrega una caja al layout.
 */
export function ConFuentes({ children }: { children: React.ReactNode }) {
	return <div className={`${inter.variable} ${geistMono.variable} contents font-sans`}>{children}</div>;
}

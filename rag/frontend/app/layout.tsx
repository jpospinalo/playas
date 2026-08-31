import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import "./globals.css";

// Fuentes auto-hospedadas (sin llamadas de red en build/runtime).
// Mismos archivos que sirven next/font/google para Inter/Geist Mono con
// subset "latin" — Inter-Variable.woff2 extraído del paquete npm oficial
// @fontsource-variable/inter (Fontsource, licencia OFL — ver
// ./fonts/Inter-OFL-LICENSE.txt); GeistMono-Variable.woff2 extraído del
// paquete npm oficial "geist" (Vercel), ya una dependencia del proyecto
// (licencia OFL — ver ./fonts/Geist-OFL-LICENSE.txt).
const inter = localFont({
	src: "./fonts/Inter-Variable.woff2",
	variable: "--font-sans",
	weight: "100 900",
	display: "swap",
});

const geistMono = localFont({
	src: "./fonts/GeistMono-Variable.woff2",
	variable: "--font-mono",
	weight: "100 900",
	display: "swap",
});

export const metadata: Metadata = {
	title: {
		default: "ATLAS — Normatividad y jurisprudencia costera",
		template: "%s | ATLAS",
	},
	description:
		"Consulta normatividad y jurisprudencia colombiana sobre playas, zonas costeras, derechos, pesca, turismo y procedimientos, con fuentes verificables.",
	openGraph: {
		type: "website",
		locale: "es_CO",
		siteName: "ATLAS",
		title: "ATLAS — Normatividad y jurisprudencia costera",
		description:
			"Consulta normatividad y jurisprudencia colombiana sobre playas y derecho costero, con citas verificables a las fuentes recuperadas.",
	},
	twitter: {
		card: "summary",
		title: "ATLAS",
		description:
			"Normatividad y jurisprudencia costera colombiana con fuentes verificables.",
	},
};

export const viewport: Viewport = {
	themeColor: [
		{ media: "(prefers-color-scheme: light)", color: "#f5fafa" },
		{ media: "(prefers-color-scheme: dark)", color: "#070d12" },
	],
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html
			lang="es"
			className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
			suppressHydrationWarning
		>
			<body className="min-h-full flex flex-col bg-background text-foreground">
				{/* Enlace de salto: primer elemento enfocable del documento. Oculto
				    visualmente hasta recibir foco (Tab desde el inicio de la
				    página); apunta al `id="main-content"` que cada vista coloca en
				    su propio landmark `<main>` (ver ChatInterface, admin layout y
				    app/about/page.tsx). El wrapper de abajo no lleva ese id: es un
				    `<div>` sin semántica de landmark, para no duplicar el id con
				    el `<main id="main-content">` propio de cada vista. */}
				<a
					href="#main-content"
					className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-full focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-accent-fg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
				>
					Saltar al contenido principal
				</a>
				<ThemeProvider>
					<AuthProvider>
						<div className="contents">{children}</div>
					</AuthProvider>
				</ThemeProvider>
			</body>
		</html>
	);
}

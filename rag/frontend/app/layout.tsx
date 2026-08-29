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
				<ThemeProvider>
					<AuthProvider>
						<div id="main-content" className="contents">
							{children}
						</div>
					</AuthProvider>
				</ThemeProvider>
			</body>
		</html>
	);
}

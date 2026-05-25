import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import "./globals.css";

const geist = Geist({
	variable: "--font-sans",
	subsets: ["latin"],
	display: "swap",
});

const geistMono = Geist_Mono({
	variable: "--font-mono",
	subsets: ["latin"],
	display: "swap",
});

export const metadata: Metadata = {
	title: {
		default: "ATLAS — Jurisprudencia costera de Colombia",
		template: "%s | ATLAS",
	},
	description:
		"ATLAS traduce la jurisprudencia colombiana sobre playas y derecho costero a respuestas claras para cualquier persona, con citas verificables a sentencias del Consejo de Estado.",
	openGraph: {
		type: "website",
		locale: "es_CO",
		siteName: "ATLAS",
		title: "ATLAS — Jurisprudencia costera de Colombia",
		description:
			"Consulta jurisprudencia colombiana sobre playas y derecho costero. Respuestas claras, con citas a sentencias verificables del Consejo de Estado.",
	},
	twitter: {
		card: "summary",
		title: "ATLAS",
		description:
			"Jurisprudencia costera colombiana, explicada para cualquier persona.",
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
			className={`${geist.variable} ${geistMono.variable} h-full antialiased`}
			suppressHydrationWarning
		>
			<body className="min-h-full flex flex-col bg-background text-foreground">
				<a href="#main-content" className="skip-link">
					Saltar al contenido principal
				</a>
				<ThemeProvider>
					<AuthProvider>{children}</AuthProvider>
				</ThemeProvider>
			</body>
		</html>
	);
}

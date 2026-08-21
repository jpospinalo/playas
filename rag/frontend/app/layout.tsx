import type { Metadata, Viewport } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import "./globals.css";

const inter = Inter({
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

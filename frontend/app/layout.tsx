import type { Metadata, Viewport } from "next";
import { EB_Garamond, Inter } from "next/font/google";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import "./globals.css";

const ebGaramond = EB_Garamond({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
});

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "ATLAS — Jurisprudencia Costera de Colombia",
    template: "%s | ATLAS",
  },
  description:
    "ATLAS es un asistente agéntico que permite consultar jurisprudencia colombiana sobre playas, dominio público marítimo-terrestre y normatividad costera mediante un pipeline RAG con citas verificadas.",
  openGraph: {
    type: "website",
    locale: "es_CO",
    siteName: "ATLAS",
    title: "ATLAS — Jurisprudencia Costera de Colombia",
    description:
      "Consulte jurisprudencia colombiana sobre playas y derecho costero con respuestas fundamentadas en fuentes verificadas del Consejo de Estado.",
  },
  twitter: {
    card: "summary",
    title: "ATLAS",
    description: "Jurisprudencia costera colombiana con IA fundamentada en fuentes verificadas.",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf7f0" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1621" },
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
      className={`${ebGaramond.variable} ${inter.variable} h-full antialiased`}
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

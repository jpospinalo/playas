import type { Metadata, Viewport } from "next";
import { EB_Garamond, Lato } from "next/font/google";
import "./globals.css";

const ebGaramond = EB_Garamond({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
});

const lato = Lato({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["300", "400", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "RAG Playas — Jurisprudencia Costera de Colombia",
    template: "%s | RAG Playas",
  },
  description:
    "Consulte jurisprudencia colombiana en materia de playas, bienes de uso público costero y derecho marítimo mediante inteligencia artificial fundamentada en fuentes verificadas.",
  openGraph: {
    type: "website",
    locale: "es_CO",
    siteName: "RAG Playas",
    title: "RAG Playas — Jurisprudencia Costera de Colombia",
    description:
      "Respuestas jurídicas fundamentadas en jurisprudencia colombiana verificada sobre playas y derecho marítimo.",
  },
  twitter: {
    card: "summary",
    title: "RAG Playas",
    description: "Jurisprudencia costera colombiana con IA.",
  },
};

export const viewport: Viewport = {
  themeColor: "#1E3A8A",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${ebGaramond.variable} ${lato.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <a href="#main-content" className="skip-link">
          Saltar al contenido principal
        </a>
        {children}
      </body>
    </html>
  );
}

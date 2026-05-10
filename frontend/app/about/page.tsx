import type { Metadata } from "next";
import { AboutNav } from "@/components/about/AboutNav";
import { AboutHero } from "@/components/about/AboutHero";
import { HowItWorks } from "@/components/about/HowItWorks";
import { WhyRag } from "@/components/about/WhyRag";
import { AboutFooter } from "@/components/about/AboutFooter";

export const metadata: Metadata = {
  title: "Cómo funciona ATLAS",
  description:
    "ATLAS utiliza una arquitectura RAG híbrida sobre sentencias del Consejo de Estado para responder consultas sobre jurisprudencia costera colombiana con citas verificadas.",
};

export default function AboutPage() {
  return (
    <>
      <AboutNav />
      <main id="main-content" className="flex flex-1 flex-col">
        <AboutHero />
        <div className="mx-auto w-full max-w-5xl px-6" aria-hidden="true">
          <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
        </div>
        <HowItWorks />
        <div className="mx-auto w-full max-w-5xl px-6" aria-hidden="true">
          <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
        </div>
        <WhyRag />
      </main>
      <AboutFooter />
    </>
  );
}

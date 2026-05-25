import type { Metadata } from "next";
import { AboutNav } from "@/components/about/AboutNav";
import { AboutHero } from "@/components/about/AboutHero";
import { HowItWorks } from "@/components/about/HowItWorks";
import { WhyRag } from "@/components/about/WhyRag";
import { AboutFooter } from "@/components/about/AboutFooter";

export const metadata: Metadata = {
  title: "Cómo funciona ATLAS",
  description:
    "ATLAS lee sentencias del Consejo de Estado sobre playas y derecho costero, y te las traduce a un lenguaje claro con citas verificables.",
};

export default function AboutPage() {
  return (
    <>
      <AboutNav />
      <main id="main-content" className="flex flex-1 flex-col">
        <AboutHero />
        <HowItWorks />
        <WhyRag />
      </main>
      <AboutFooter />
    </>
  );
}

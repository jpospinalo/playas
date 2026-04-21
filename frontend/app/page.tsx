import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { LandingNav } from "@/components/landing/LandingNav";
import { WhyRag } from "@/components/landing/WhyRag";

export default function LandingPage() {
  return (
    <>
      <LandingNav />
      <main id="main-content" className="flex flex-1 flex-col">
        <Hero />
        <div className="mx-auto w-full max-w-5xl px-6" aria-hidden="true">
          <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
        </div>
        <HowItWorks />
        <div className="mx-auto w-full max-w-5xl px-6" aria-hidden="true">
          <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
        </div>
        <WhyRag />
      </main>
      <LandingFooter />
    </>
  );
}

import Image from "next/image";

export function AboutFooter() {
	return (
		<footer className="mt-12 border-t border-border/60">
			<div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-y-3 px-4 py-8 text-xs text-subtle sm:px-6 lg:px-10 xl:px-16">
				<span className="flex items-center gap-1.5">
					<span
						className="font-medium tracking-[0.18em] text-foreground"
						translate="no"
					>
						ATLAS
					</span>
					<span aria-hidden="true">·</span>
					<span>© {new Date().getFullYear()}</span>
				</span>

				<div className="flex items-center gap-3">
					<span>Jurisprudencia costera colombiana</span>
					<span aria-hidden="true" className="text-border">
						|
					</span>
					<a
						href="https://www.usergioarboleda.edu.co"
						target="_blank"
						rel="noopener noreferrer"
						className="flex items-center gap-2 opacity-80 transition-opacity hover:opacity-100"
						aria-label="Universidad Sergio Arboleda"
					>
						<Image
							src="/brand/usa-logo.png"
							alt="Universidad Sergio Arboleda"
							width={64}
							height={71}
							className="h-6 w-auto shrink-0"
						/>
						<span>Universidad Sergio Arboleda</span>
					</a>
				</div>
			</div>
		</footer>
	);
}

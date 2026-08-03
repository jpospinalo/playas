import Image from "next/image";

export function AtlasWordmark({
	className = "",
	iconSize = 24,
}: {
	className?: string;
	iconSize?: number;
}) {
	return (
		<span className={`inline-flex items-center gap-2 ${className}`}>
			<Image
				src="/brand/atlas-icon.png"
				alt=""
				width={iconSize}
				height={iconSize}
				className="shrink-0 rounded-full"
				priority
			/>
			<span
				className="font-medium tracking-[0.18em] uppercase leading-none text-foreground"
				translate="no"
			>
				ATLAS
			</span>
		</span>
	);
}

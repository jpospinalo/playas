import type { SourceMetadata } from "@/lib/types";

const NORMATIVE_LABELS = [
	["titulo", "Título"],
	["capitulo", "Capítulo"],
	["articulo", "Artículo"],
] as const;

/** Hierarchy belongs to the cited fragment, not to every article in its file. */
export function normativeAttribution(
	fragment: SourceMetadata,
	legacyGroup: SourceMetadata,
): Array<{ label: string; value: string }> {
	// Older saved groups can carry the hierarchy only at document level.
	// Do not merge those fields into a partially described current fragment.
	const metadata = NORMATIVE_LABELS.some(
		([key]) => typeof fragment[key] === "string" && fragment[key].trim(),
	)
		? fragment
		: legacyGroup;
	return NORMATIVE_LABELS.flatMap(([key, label]) => {
		const value = metadata[key];
		return typeof value === "string" && value ? [{ label, value }] : [];
	});
}

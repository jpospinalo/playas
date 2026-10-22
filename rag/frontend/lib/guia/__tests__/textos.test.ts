import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { textosConAudio } from "@/lib/guia/textos";
import { claveAudio } from "@/lib/voz";

const AUDIO = path.resolve(__dirname, "../../../public/audio");

describe("audios grabados de los textos fijos", () => {
	it("cada texto fijo tiene su audio (si un texto cambia, hay que volver a generarlo)", () => {
		const manifiesto = JSON.parse(readFileSync(path.join(AUDIO, "manifest.json"), "utf8")) as Record<string, string>;
		const porClave = new Map(Object.entries(manifiesto).map(([t, f]) => [claveAudio(t), f]));
		const faltan = textosConAudio().filter((t) => {
			const archivo = porClave.get(claveAudio(t));
			return !archivo || !existsSync(path.join(AUDIO, archivo));
		});
		expect(faltan).toEqual([]);
	});
});

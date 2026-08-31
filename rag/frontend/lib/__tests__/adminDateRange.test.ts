import { describe, expect, it } from "vitest";
import {
	colombiaEndOfDayIso,
	colombiaStartOfDayIso,
	isValidDateRange,
	isValidNumericRange,
} from "@/lib/adminDateRange";

describe("colombiaStartOfDayIso / colombiaEndOfDayIso (A3)", () => {
	it("produce el inicio del día en UTC-5, no medianoche UTC", () => {
		const iso = colombiaStartOfDayIso("2026-01-15");
		expect(iso).toBe("2026-01-15T00:00:00.000-05:00");
		// Instante real en UTC: 5 horas después de medianoche Colombia.
		expect(new Date(iso).toISOString()).toBe("2026-01-15T05:00:00.000Z");
	});

	it("produce el final del día en UTC-5", () => {
		const iso = colombiaEndOfDayIso("2026-01-15");
		expect(iso).toBe("2026-01-15T23:59:59.999-05:00");
		expect(new Date(iso).toISOString()).toBe("2026-01-16T04:59:59.999Z");
	});
});

describe("isValidDateRange (A3)", () => {
	it("acepta un rango donde inicio <= fin", () => {
		expect(isValidDateRange("2026-01-01", "2026-01-31")).toBe(true);
		expect(isValidDateRange("2026-01-15", "2026-01-15")).toBe(true);
	});

	it("rechaza un rango donde inicio > fin", () => {
		expect(isValidDateRange("2026-02-01", "2026-01-01")).toBe(false);
	});

	it("no valida si falta un extremo", () => {
		expect(isValidDateRange("", "2026-01-01")).toBe(true);
		expect(isValidDateRange("2026-01-01", "")).toBe(true);
		expect(isValidDateRange("", "")).toBe(true);
	});
});

describe("isValidNumericRange (A3)", () => {
	it("acepta mínimo <= máximo", () => {
		expect(isValidNumericRange("2", "4")).toBe(true);
		expect(isValidNumericRange("3", "3")).toBe(true);
	});

	it("rechaza mínimo > máximo", () => {
		expect(isValidNumericRange("4", "2")).toBe(false);
	});

	it("no valida si falta un extremo", () => {
		expect(isValidNumericRange("", "4")).toBe(true);
		expect(isValidNumericRange("2", "")).toBe(true);
	});
});

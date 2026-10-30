import { describe, expect, it } from "vitest";
import { forgetEmail, getLastEmail, rememberEmail } from "@/lib/auth";

describe("forgetEmail (celular compartido, QA E2-11)", () => {
	it("olvida el correo recordado para la pantalla de ingreso", () => {
		rememberEmail("p001@ejercicio.atlas");
		expect(getLastEmail()).toBe("p001@ejercicio.atlas");
		forgetEmail();
		expect(getLastEmail()).toBe("");
	});
});

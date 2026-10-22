import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Infraestructura mínima de pruebas (G1, plan v1.1 de corrección del
// frontend). Sin capa de cobertura obligatoria todavía: la aceptación se
// basa en los escenarios críticos declarados en el plan, no en un
// porcentaje global — ver rag/frontend/AGENTS.md y el plan de corrección.
export default defineConfig({
	plugins: [react()],
	resolve: {
		alias: {
			// Mismo alias que tsconfig.json ("@/*" -> "./*"), reproducido aquí
			// sin depender de una biblioteca adicional (vite-tsconfig-paths).
			"@": path.resolve(__dirname, "."),
			// next/font solo existe dentro del compilador de Next.
			"next/font/local": path.resolve(__dirname, "__mocks__/next-font-local.ts"),
		},
	},
	test: {
		environment: "jsdom",
		globals: true,
		setupFiles: ["./vitest.setup.ts"],
		include: ["**/*.test.{ts,tsx}"],
		exclude: ["node_modules", ".next"],
	},
});

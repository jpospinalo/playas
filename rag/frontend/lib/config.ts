/**
 * Normaliza el valor crudo de `NEXT_PUBLIC_API_URL` al string que se usa
 * como prefijo de cada llamada al API (`${API_URL}/api/...`).
 *
 * Contratos que debe preservar (A1, plan de corrección del frontend v1.1):
 *   - Variable no definida (`undefined`): usar el valor de desarrollo por
 *     defecto `http://localhost:8080`.
 *   - Variable definida como cadena vacía (`""`): NO caer al valor por
 *     defecto — conservar `""` tal cual, para que `${API_URL}/api/...`
 *     produzca rutas relativas (`/api/...`), el modo de despliegue detrás
 *     de un proxy inverso que sirve frontend y backend bajo el mismo
 *     origen. El operador `||` usado antes trataba `""` como valor "vacío"
 *     y caía al fallback de desarrollo, rompiendo ese despliegue.
 *   - URL no vacía: se retiran únicamente las barras finales redundantes
 *     (una o varias), sin tocar el resto del valor — nunca se fuerza
 *     `https://`, eso es responsabilidad de quien configura la variable.
 */
export function normalizeApiUrl(raw: string | undefined): string {
	if (raw === undefined) {
		return "http://localhost:8080";
	}
	if (raw === "") {
		return "";
	}
	return raw.replace(/\/+$/, "");
}

export const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);

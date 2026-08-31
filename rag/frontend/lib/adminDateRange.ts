/**
 * A3 — conversión de un `<input type="date">` (`YYYY-MM-DD`, sin zona
 * horaria) al ISO 8601 que espera el backend, interpretando el valor como
 * un día calendario de Colombia (UTC-5). Colombia no observa horario de
 * verano, así que el offset es constante durante todo el año — no hace
 * falta ninguna biblioteca de fechas para esta conversión.
 *
 * El código anterior usaba `new Date(dateStr).toISOString()`: como
 * `dateStr` es una fecha sin hora, el motor JS la interpreta como
 * medianoche UTC, no medianoche de Colombia — el rango real quedaba
 * desplazado 5 horas respecto al día calendario que el usuario seleccionó.
 */
export function colombiaStartOfDayIso(dateStr: string): string {
	return `${dateStr}T00:00:00.000-05:00`;
}

export function colombiaEndOfDayIso(dateStr: string): string {
	return `${dateStr}T23:59:59.999-05:00`;
}

/**
 * `true` si `start`/`end` (formato `YYYY-MM-DD`, o cadena vacía si no se
 * fijó ese extremo) forman un rango válido. Vacío en cualquiera de los dos
 * lados no es un error — solo se valida cuando ambos están presentes. La
 * comparación lexicográfica de strings es válida para este formato porque
 * es de ancho fijo y de mayor a menor significancia (año-mes-día).
 */
export function isValidDateRange(start: string, end: string): boolean {
	if (!start || !end) return true;
	return start <= end;
}

/**
 * Igual que `isValidDateRange`, para pares mínimo/máximo numéricos (p. ej.
 * calificaciones 1–5) representados como string por venir de un `<select>`.
 */
export function isValidNumericRange(min: string, max: string): boolean {
	if (!min || !max) return true;
	return Number(min) <= Number(max);
}

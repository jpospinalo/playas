"use client";

/**
 * J6-A9: todo filtro tiene su contraria a la vista. Aparece al final de la fila
 * de controles solo cuando hay algún filtro puesto (al final, para no mover a
 * los demás controles).
 */
export function LimpiarFiltros({ activo, onLimpiar }: { activo: boolean; onLimpiar: () => void }) {
	if (!activo) return null;
	return (
		<button type="button" className="pnl-btn-sec pnl-limpiar" onClick={onLimpiar}>
			Limpiar filtros
		</button>
	);
}

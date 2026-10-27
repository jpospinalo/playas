"use client";

/**
 * J6-A9: todo filtro tiene su contraria a la vista. Sin filtros puestos el
 * botón guarda su lugar pero no se ve ni se enfoca (J6-A4: al aparecer no
 * mueve a los demás controles, ni en filas alineadas a la derecha).
 */
export function LimpiarFiltros({ activo, onLimpiar }: { activo: boolean; onLimpiar: () => void }) {
	return (
		<button
			type="button"
			className={activo ? "pnl-btn-sec pnl-limpiar" : "pnl-btn-sec pnl-limpiar pnl-limpiar-oculto"}
			onClick={onLimpiar}
			disabled={!activo}
			aria-hidden={!activo || undefined}
			tabIndex={activo ? undefined : -1}
		>
			Limpiar filtros
		</button>
	);
}

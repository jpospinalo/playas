"use client";

import { PERIODOS } from "@/lib/admin/panel";

/** Selector de periodo (7 / 30 / 90 días / Todo), igual en todo el panel. */
export function Periodo({ dias, onCambio }: { dias: number; onCambio: (d: number) => void }) {
	return (
		<fieldset className="pnl-periodo">
			<legend>Periodo</legend>
			<div className="pnl-seg">
				{PERIODOS.map((p) => (
					<label key={p.dias}>
						<input
							type="radio"
							name="periodo"
							value={p.dias}
							checked={dias === p.dias}
							onChange={() => onCambio(p.dias)}
						/>
						<span>{p.texto}</span>
					</label>
				))}
			</div>
		</fieldset>
	);
}

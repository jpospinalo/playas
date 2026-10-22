// next/font solo funciona dentro del compilador de Next; en vitest se
// reemplaza por un objeto con la misma forma (ver vitest.config.ts).
export default function localFont(opciones: { variable?: string }) {
	return { className: "", variable: opciones.variable ?? "", style: { fontFamily: "" } };
}

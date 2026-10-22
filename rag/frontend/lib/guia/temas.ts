/**
 * Contenido del flujo guiado (diseño v3): temas, opciones de "¿Qué le pasó?"
 * y la pregunta que se le envía al RAG por cada opción.
 *
 * Aquí no hay contenido legal: solo las preguntas. La respuesta siempre sale
 * del backend. `pregunta` es lo que se envía y queda guardado en la
 * conversación; `texto` es lo que ve la persona en el botón.
 */

export type IconoTema = "caminar" | "pez" | "venta" | "hotel" | "lancha" | "obra";

export interface OpcionTema {
	texto: string;
	pregunta: string;
	/** Pide la playa antes de preguntar (la respuesta cambia según la playa). */
	pidePlaya?: boolean;
}

export interface Tema {
	id: string;
	icono: IconoTema;
	titulo: string;
	detalle: string;
	/** Título de la pantalla de opciones. */
	pantalla: string;
	opciones: OpcionTema[];
}

export const PLAYAS = [
	"Taganga",
	"Bahía de Santa Marta",
	"Playa Blanca",
	"El Rodadero",
	"Bello Horizonte",
	"Pozos Colorados",
] as const;

export const TEMAS: Tema[] = [
	{
		id: "entrar",
		icono: "caminar",
		titulo: "Entrar o caminar por la playa",
		detalle: "Le cerraron el paso, le cobran o le piden salir",
		pantalla: "¿Qué le pasó?",
		opciones: [
			{
				texto: "Un hotel o negocio no me deja pasar",
				pregunta:
					"Un hotel o un negocio no me deja pasar a la playa. ¿Puede impedirme el paso a la playa?",
			},
			{
				texto: "Me quieren cobrar por entrar",
				pregunta: "Me quieren cobrar por entrar a la playa. ¿Pueden cobrar por el acceso a la playa?",
			},
			{
				texto: "Me piden que me vaya de la playa",
				pregunta:
					"Me piden que me vaya de la playa. ¿En qué casos me pueden pedir que salga de una playa?",
			},
		],
	},
	{
		id: "pescar",
		icono: "pez",
		titulo: "Pescar",
		detalle: "Dónde, cuándo y con qué se puede pescar",
		pantalla: "¿Qué quiere saber?",
		opciones: [
			{
				texto: "Si puedo pescar frente a un hotel",
				pregunta: "¿Puedo pescar en la playa o en el mar frente a un hotel?",
			},
			{
				texto: "Qué permiso necesito para pescar",
				pregunta: "¿Qué permiso necesito para pescar en el mar o en la playa?",
			},
		],
	},
	{
		id: "vender",
		icono: "venta",
		titulo: "Vender en la playa",
		detalle: "Permisos y lugares para vender",
		pantalla: "¿Qué quiere saber?",
		opciones: [
			{
				texto: "Qué permiso necesito para vender",
				pregunta: "¿Qué permiso necesito para vender en la playa?",
				pidePlaya: true,
			},
			{
				texto: "En qué parte de la playa puedo vender",
				pregunta: "¿En qué parte de la playa se puede vender?",
				pidePlaya: true,
			},
		],
	},
	{
		id: "hoteles",
		icono: "hotel",
		titulo: "Hoteles y negocios frente al mar",
		detalle: "Qué pueden usar y qué no",
		pantalla: "¿Qué quiere saber?",
		opciones: [
			{
				texto: "Si un hotel puede poner sillas y carpas en la arena",
				pregunta: "¿Un hotel puede poner sillas y carpas en la arena de la playa?",
			},
			{
				texto: "Si un hotel puede cerrar la playa",
				pregunta: "¿Un hotel puede cerrar o encerrar una parte de la playa?",
			},
		],
	},
	{
		id: "lanchas",
		icono: "lancha",
		titulo: "Lanchas, motos de agua y bañistas",
		detalle: "Por dónde pueden andar",
		pantalla: "¿Qué quiere saber?",
		opciones: [
			{
				texto: "Por dónde pueden andar las lanchas",
				pregunta: "¿Por dónde pueden andar las lanchas y las motos de agua cerca de la playa?",
			},
			{
				texto: "Hasta dónde se puede bañar la gente",
				pregunta: "¿Hasta dónde se pueden bañar las personas en la playa? ¿Cómo se separa la zona de bañistas?",
			},
		],
	},
	{
		id: "obras",
		icono: "obra",
		titulo: "Construcciones cerca del mar",
		detalle: "Qué se puede construir y qué no",
		pantalla: "¿Qué quiere saber?",
		opciones: [
			{
				texto: "Si se puede construir sobre la arena",
				pregunta: "¿Se puede construir sobre la arena de la playa?",
			},
		],
	},
];

export function buscarTema(id: string | undefined): Tema | null {
	return TEMAS.find((t) => t.id === id) ?? null;
}

/**
 * Pregunta final para el RAG. La playa se agrega en lenguaje natural para
 * que la recuperación la tenga en cuenta, sin cambiar la pregunta base.
 */
export function preguntaConPlaya(pregunta: string, playa: string | null): string {
	if (!playa) return pregunta;
	return `${pregunta} Es en ${playa}, en Santa Marta.`;
}

import type { Metadata } from "next";
import { GuiaApp } from "@/components/guia/GuiaApp";
import "./guia.css";

export const metadata: Metadata = {
	title: "ATLAS: preguntas sobre las playas de Santa Marta",
	description:
		"Pregunte, con palabras sencillas, qué dicen las normas y los jueces de Colombia sobre las playas: entrar, pescar, vender, hoteles, lanchas y construcciones.",
};

export default function InicioPage() {
	return <GuiaApp />;
}

import type { Metadata } from "next";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { ConFuentes } from "@/components/common/ConFuentes";

// Chat completo (historial, calificación detallada, comentarios), para el
// equipo. El público entra por el flujo guiado de la portada (/).
export const metadata: Metadata = {
	title: "Chat del equipo",
	robots: { index: false },
};

export default function ChatPage() {
	return (
		<ConFuentes>
			<div className="flex h-dvh flex-col overflow-hidden bg-background">
				<ChatInterface />
			</div>
		</ConFuentes>
	);
}

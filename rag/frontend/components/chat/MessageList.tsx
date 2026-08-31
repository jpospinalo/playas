import type { Message } from "@/lib/types";
import { AssistantBubble } from "@/components/chat/AssistantBubble";
import { UserBubble } from "@/components/chat/UserBubble";

interface MessageListProps {
	messages: Message[];
	ratedMessageIds: Set<string>;
	/** A5 — IDs de mensajes de asistente cuyo reintento de guardado está en curso. */
	persistingMessageIds?: Set<string>;
	/** A5 — reintenta guardar una respuesta con `persistenceStatus: "failed"`. */
	onRetryPersist?: (messageId: string) => void;
	onMessageRate: (
		messageId: string,
		ratings: { pertinence: number; accuracy: number },
		expectedAnswer?: string,
	) => Promise<void>;
}

export function MessageList({
	messages,
	ratedMessageIds,
	persistingMessageIds,
	onRetryPersist,
	onMessageRate,
}: MessageListProps) {
	// Lista semántica en vez de un Fragment transparente: cada mensaje es
	// un `<li>` de un `<ul>` real, en vez de dejar que los globos queden
	// como hijos directos e indistinguibles del contenedor de
	// ChatInterface. `aria-label` le da un nombre accesible propio a esta
	// lista (distinto del encabezado de página) para que un lector de
	// pantalla en modo de navegación por landmarks/listas la identifique
	// como el historial de la conversación. Deliberadamente SIN
	// `role="log"` ni `aria-live` en este contenedor: el texto llega
	// token a token durante el streaming (ver AssistantBubble), y una
	// región viva aquí anunciaría cada fragmento parcial según va
	// llegando en vez de la respuesta completa; el anuncio de
	// progreso/finalización ya lo cubre la región de estado dedicada en
	// ChatInterface (`streamingStatus`).
	//
	// `space-y-8` se repite aquí, en el propio `<ul>`: antes, al devolver
	// este componente un Fragment transparente, el `space-y-8` del
	// contenedor de ChatInterface aplicaba directamente entre cada globo
	// (eran hijos directos de ese contenedor). Ahora que viven dentro de un
	// `<ul>` real, ese `space-y-8` del contenedor de ChatInterface solo
	// separa al `<ul>` en su conjunto de sus hermanos (burbuja de carga,
	// aviso de error, aviso de generación detenida): el espaciado vertical
	// ENTRE mensajes individuales necesita su propia copia de la utilidad
	// aquí, en el `<ul>`, para que el resultado visual no cambie.
	return (
		<ul className="space-y-8" aria-label="Historial de mensajes">
			{messages
				.filter((msg) => msg.text.length > 0)
				.map((msg) => (
					<li key={msg.id}>
						{msg.role === "user" ? (
							<UserBubble text={msg.text} />
						) : (
							<AssistantBubble
								text={msg.text}
								sources={msg.sources ?? []}
								messageId={msg.id}
								isRated={ratedMessageIds.has(msg.id)}
								persistenceFailed={msg.persistenceStatus === "failed"}
								retryingPersist={persistingMessageIds?.has(msg.id) ?? false}
								onRetryPersist={() => onRetryPersist?.(msg.id)}
								onRate={onMessageRate}
							/>
						)}
					</li>
				))}
		</ul>
	);
}

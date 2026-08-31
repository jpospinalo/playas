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
	return (
		<>
			{messages.map(
				(msg) =>
					msg.text.length > 0 &&
					(msg.role === "user" ? (
						<UserBubble key={msg.id} text={msg.text} />
					) : (
						<AssistantBubble
							key={msg.id}
							text={msg.text}
							sources={msg.sources ?? []}
							messageId={msg.id}
							isRated={ratedMessageIds.has(msg.id)}
							persistenceFailed={msg.persistenceStatus === "failed"}
							retryingPersist={persistingMessageIds?.has(msg.id) ?? false}
							onRetryPersist={() => onRetryPersist?.(msg.id)}
							onRate={onMessageRate}
						/>
					)),
			)}
		</>
	);
}

import type { Message } from "@/lib/types";
import { AssistantBubble } from "@/components/chat/AssistantBubble";
import { UserBubble } from "@/components/chat/UserBubble";

interface MessageListProps {
	messages: Message[];
	conversationId: string;
	ratedMessageIds: Set<string>;
	onMessageRate: (
		messageId: string,
		ratings: { pertinence: number; accuracy: number },
		expectedAnswer?: string,
	) => Promise<void>;
}

export function MessageList({
	messages,
	conversationId,
	ratedMessageIds,
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
							conversationId={conversationId}
							isRated={ratedMessageIds.has(msg.id)}
							onRate={onMessageRate}
						/>
					)),
			)}
		</>
	);
}

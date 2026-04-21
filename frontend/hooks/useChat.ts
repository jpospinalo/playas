"use client";

import { useRef, useState } from "react";
import { queryRagStream } from "@/lib/api";
import type { AgentStage, Message } from "@/lib/types";

export interface UseChatReturn {
  messages: Message[];
  input: string;
  loading: boolean;
  isStreaming: boolean;
  stage: AgentStage | null;
  stageMessage: string | null;
  error: string | null;
  /** Porcentaje de la ventana de contexto consumida (0–100). */
  contextPercent: number;
  setInput: (value: string) => void;
  submit: (question: string) => Promise<void>;
  resetChat: () => void;
}

const DEFAULT_STAGE_MESSAGES: Record<AgentStage, string> = {
  enriching: "Reformulando la consulta…",
  retrieving: "Buscando jurisprudencia relevante…",
  generating: "Analizando las sentencias…",
};

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [stage, setStage] = useState<AgentStage | null>(null);
  const [stageMessage, setStageMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contextPercent, setContextPercent] = useState(0);
  // Stable thread_id for the entire chat session. Regenerated on resetChat().
  const threadIdRef = useRef<string>(crypto.randomUUID());
  // Track whether the first token has been received to flip isStreaming exactly once.
  const streamingStartedRef = useRef(false);

  async function submit(question: string): Promise<void> {
    const q = question.trim();
    if (!q || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text: q },
    ]);
    setInput("");
    setLoading(true);
    setIsStreaming(false);
    setStage(null);
    setStageMessage(null);
    setError(null);
    streamingStartedRef.current = false;

    // Insert assistant placeholder before streaming starts so the user
    // sees the response area appear immediately.
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", text: "", sources: [] },
    ]);

    try {
      for await (const event of queryRagStream({ question: q, thread_id: threadIdRef.current })) {
        if (event.type === "token") {
          // Flip to streaming on first token so LoadingBubble disappears.
          if (!streamingStartedRef.current) {
            streamingStartedRef.current = true;
            setIsStreaming(true);
            setStage(null);
            setStageMessage(null);
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, text: m.text + event.content }
                : m
            )
          );
        } else if (event.type === "status") {
          setStage(event.stage);
          setStageMessage(event.message ?? DEFAULT_STAGE_MESSAGES[event.stage]);
        } else if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources: event.sources } : m
            )
          );
          if (event.context_tokens != null && event.context_limit) {
            setContextPercent(Math.round((event.context_tokens / event.context_limit) * 100));
          }
        } else if (event.type === "error") {
          throw new Error(event.detail);
        }
      }
    } catch (err) {
      // Remove the empty placeholder on error so the UI stays clean.
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      setError(
        err instanceof Error
          ? err.message
          : "Error de conexión. Compruebe que el servidor está activo."
      );
    } finally {
      setLoading(false);
      setIsStreaming(false);
      setStage(null);
      setStageMessage(null);
    }
  }

  function resetChat(): void {
    setMessages([]);
    setInput("");
    setLoading(false);
    setIsStreaming(false);
    setStage(null);
    setStageMessage(null);
    setError(null);
    setContextPercent(0);
    streamingStartedRef.current = false;
    threadIdRef.current = crypto.randomUUID();
  }

  return {
    messages,
    input,
    loading,
    isStreaming,
    stage,
    stageMessage,
    error,
    contextPercent,
    setInput,
    submit,
    resetChat,
  };
}

"use client";

import { useRef, useState } from "react";
import {
  addDoc,
  collection,
  doc,
  getDocs,
  increment,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  updateDoc,
} from "firebase/firestore";
import { generateConversationTitle, queryRagStream } from "@/lib/api";
import { db } from "@/lib/firebase";
import type { AgentStage, Message, SourceGroup } from "@/lib/types";
import { normalizeSources } from "@/lib/types";
import { useAuth } from "@/components/providers/AuthProvider";
import type { Conversation } from "@/hooks/useConversations";

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
  /** ID del documento de conversación activo en Firestore (null si no hay sesión o aún no se creó). */
  conversationId: string | null;
  setInput: (value: string) => void;
  submit: (question: string) => Promise<void>;
  resetChat: () => void;
  loadConversation: (conv: Conversation) => Promise<void>;
}

const DEFAULT_STAGE_MESSAGES: Record<AgentStage, string> = {
  enriching: "Reformulando la consulta…",
  retrieving: "Buscando jurisprudencia relevante…",
  generating: "Analizando las sentencias…",
};

export function useChat(): UseChatReturn {
  const { user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [stage, setStage] = useState<AgentStage | null>(null);
  const [stageMessage, setStageMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contextPercent, setContextPercent] = useState(0);
  const [conversationId, setConversationId] = useState<string | null>(null);

  // Stable thread_id for the entire chat session. Regenerated on resetChat().
  const threadIdRef = useRef<string>(crypto.randomUUID());
  // Mirrors conversationId state for use inside async callbacks without stale closures.
  const conversationIdRef = useRef<string | null>(null);
  // Track whether the first token has been received to flip isStreaming exactly once.
  const streamingStartedRef = useRef(false);

  function _setConversationId(id: string | null) {
    conversationIdRef.current = id;
    setConversationId(id);
  }

  /** Crea el documento de conversación en Firestore al enviar el primer mensaje. */
  async function _createConversation(firstQuestion: string): Promise<string> {
    if (!user) return "";
    const newRef = doc(collection(db, "conversations"));
    const now = new Date();
    const dateStr = now.toLocaleDateString("es-CO", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const timeStr = now.toLocaleTimeString("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
    });
    await setDoc(newRef, {
      userId: user.uid,
      threadId: threadIdRef.current,
      title: `Chat ${dateStr} ${timeStr}`,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
      messageCount: 0,
    });

    // Obtener token ahora (user no es null en este punto) y generar título en background.
    // Pasar el token directamente evita una race condition con auth.currentUser.
    user.getIdToken().then((token) => {
      generateConversationTitle(firstQuestion, newRef.id, token).catch(() => {});
    }).catch(() => {});

    return newRef.id;
  }

  async function submit(question: string): Promise<void> {
    const q = question.trim();
    if (!q || loading) return;

    // Si el usuario está autenticado y es el primer mensaje de esta sesión,
    // crear el documento de conversación en Firestore.
    const isFirstMessage = messages.length === 0 && !conversationIdRef.current;
    if (user && isFirstMessage) {
      const newConvId = await _createConversation(q);
      _setConversationId(newConvId);
    }

    const activeConvId = conversationIdRef.current;

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

    // Guardar mensaje del usuario en Firestore (fire-and-forget)
    if (user && activeConvId) {
      addDoc(collection(db, "conversations", activeConvId, "messages"), {
        role: "user",
        text: q,
        createdAt: serverTimestamp(),
      }).catch(() => {});
    }

    // Insertar placeholder del asistente para que el área de respuesta aparezca
    // de inmediato mientras llegan los tokens.
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", text: "", sources: [] },
    ]);

    let finalAssistantText = "";
    let finalAssistantSources: SourceGroup[] = [];

    try {
      for await (const event of queryRagStream({
        question: q,
        thread_id: threadIdRef.current,
        conversation_id: activeConvId ?? undefined,
      })) {
        if (event.type === "token") {
          if (!streamingStartedRef.current) {
            streamingStartedRef.current = true;
            setIsStreaming(true);
            setStage(null);
            setStageMessage(null);
          }
          finalAssistantText += event.content;
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
          const groups = normalizeSources(event.sources);
          finalAssistantSources = groups;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources: groups } : m
            )
          );
          if (event.context_tokens != null && event.context_limit) {
            setContextPercent(
              Math.round((event.context_tokens / event.context_limit) * 100)
            );
          }
        } else if (event.type === "error") {
          throw new Error(event.detail);
        }
      }

      // Persistir respuesta del asistente en Firestore (fire-and-forget)
      if (user && activeConvId && finalAssistantText) {
        addDoc(collection(db, "conversations", activeConvId, "messages"), {
          role: "assistant",
          text: finalAssistantText,
          sources:
            finalAssistantSources.length > 0 ? finalAssistantSources : null,
          createdAt: serverTimestamp(),
        }).catch(() => {});

        updateDoc(doc(db, "conversations", activeConvId), {
          updatedAt: serverTimestamp(),
          messageCount: increment(1),
        }).catch(() => {});
      }
    } catch (err) {
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

  /** Carga una conversación existente desde Firestore y la restaura en la UI. */
  async function loadConversation(conv: Conversation): Promise<void> {
    const messagesRef = query(
      collection(db, "conversations", conv.id, "messages"),
      orderBy("createdAt", "asc")
    );

    const snapshot = await getDocs(messagesRef);
    const loaded: Message[] = snapshot.docs.map((docSnap) => {
      const data = docSnap.data();
      const rawSources = data.sources;
      return {
        id: docSnap.id,
        role: data.role as "user" | "assistant",
        text: (data.text as string) ?? "",
        sources: rawSources ? normalizeSources(rawSources) : undefined,
      };
    });

    setMessages(loaded);
    threadIdRef.current = conv.threadId;
    _setConversationId(conv.id);
    setInput("");
    setLoading(false);
    setIsStreaming(false);
    setStage(null);
    setStageMessage(null);
    setError(null);
    setContextPercent(0);
    streamingStartedRef.current = false;
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
    _setConversationId(null);
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
    conversationId,
    setInput,
    submit,
    resetChat,
    loadConversation,
  };
}

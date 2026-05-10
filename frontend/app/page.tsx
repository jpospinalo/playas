import type { Metadata } from "next";
import { ChatInterface } from "@/components/chat/ChatInterface";

export const metadata: Metadata = {
  title: "ATLAS — Consulta jurisprudencia costera de Colombia",
  description:
    "Consulte jurisprudencia colombiana sobre playas, bienes de uso público costero y dominio público marítimo-terrestre. Respuestas fundamentadas en sentencias verificadas del Consejo de Estado.",
};

export default function ChatPage() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <ChatInterface />
    </div>
  );
}

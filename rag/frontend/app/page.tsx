import type { Metadata } from "next";
import { ChatInterface } from "@/components/chat/ChatInterface";

export const metadata: Metadata = {
  title: "ATLAS — Consulta normatividad y jurisprudencia costera",
  description:
    "Consulte normatividad y jurisprudencia colombiana sobre playas, bienes de uso público costero, pesca, turismo, derechos y procedimientos.",
};

export default function ChatPage() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <ChatInterface />
    </div>
  );
}

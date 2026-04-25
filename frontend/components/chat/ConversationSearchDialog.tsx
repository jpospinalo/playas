"use client";

import { useEffect, useRef, type RefObject } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Conversation } from "@/hooks/useConversations";
import { formatConversationDate } from "@/components/chat/conversationSidebarUtils";

interface ConversationSearchDialogProps {
  open: boolean;
  search: string;
  conversations: Conversation[];
  results: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onClose: () => void;
  onSelectConversation: (conv: Conversation) => Promise<void>;
}

export function ConversationSearchDialog({
  open,
  search,
  conversations,
  results,
  activeConversationId,
  loading,
  onSearchChange,
  onClose,
  onSelectConversation,
}: ConversationSearchDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hasSearch = search.trim().length > 0;

  useEffect(() => {
    if (!open) return;

    inputRef.current?.focus();

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/30 px-4 pt-[12vh] backdrop-blur-[2px]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          aria-hidden="false"
        >
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            aria-label="Cerrar búsqueda"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Buscar conversaciones"
            data-conversation-search-dialog
            className="relative z-10 flex max-h-[72vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-foreground/20"
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            <SearchHeader
              inputRef={inputRef}
              search={search}
              hasSearch={hasSearch}
              onSearchChange={onSearchChange}
              onClose={onClose}
            />

            <SearchResults
              loading={loading}
              hasSearch={hasSearch}
              conversations={conversations}
              results={results}
              activeConversationId={activeConversationId}
              onSelectConversation={onSelectConversation}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SearchHeader({
  inputRef,
  search,
  hasSearch,
  onSearchChange,
  onClose,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  search: string;
  hasSearch: boolean;
  onSearchChange: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="border-b border-border p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Buscar chats</h2>
          <p className="mt-0.5 text-xs text-muted">
            Encuentra una conversación por título y ábrela al instante.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar búsqueda"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <CloseIcon />
        </button>
      </div>

      <label htmlFor="conversation-search-dialog" className="sr-only">
        Buscar conversaciones
      </label>
      <div className="flex items-center gap-3 rounded-xl border border-border bg-background px-3 py-2.5 transition-[border-color,box-shadow] duration-150 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
        <SearchIcon className="shrink-0 text-muted" />
        <input
          ref={inputRef}
          id="conversation-search-dialog"
          type="text"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Buscar conversaciones..."
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted/60 focus:outline-none"
        />
        {hasSearch && (
          <button
            type="button"
            onClick={() => {
              onSearchChange("");
              inputRef.current?.focus();
            }}
            aria-label="Limpiar búsqueda"
            className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Limpiar
          </button>
        )}
      </div>
    </div>
  );
}

function SearchResults({
  loading,
  hasSearch,
  conversations,
  results,
  activeConversationId,
  onSelectConversation,
}: {
  loading: boolean;
  hasSearch: boolean;
  conversations: Conversation[];
  results: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (conv: Conversation) => Promise<void>;
}) {
  return (
    <div className="flex-1 overflow-y-auto p-2">
      <div className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted/70">
        {hasSearch
          ? `${results.length} resultado${results.length === 1 ? "" : "s"}`
          : "Conversaciones recientes"}
      </div>

      {loading && conversations.length === 0 && (
        <p className="px-3 py-8 text-center text-sm text-muted">
          Cargando conversaciones...
        </p>
      )}

      {!loading && results.length === 0 && <EmptySearchState />}

      {results.map((conv) => (
        <SearchResultItem
          key={conv.id}
          conversation={conv}
          active={conv.id === activeConversationId}
          onSelectConversation={onSelectConversation}
        />
      ))}
    </div>
  );
}

function SearchResultItem({
  conversation,
  active,
  onSelectConversation,
}: {
  conversation: Conversation;
  active: boolean;
  onSelectConversation: (conv: Conversation) => Promise<void>;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelectConversation(conversation)}
      className={`group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
        active
          ? "bg-accent/10 text-foreground"
          : "text-muted hover:bg-accent/6 hover:text-foreground"
      }`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background text-muted transition-colors group-hover:border-accent/30 group-hover:text-accent">
        <ChatIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {conversation.title}
        </span>
        <span className="mt-0.5 block text-xs text-muted/70">
          {formatConversationDate(conversation.updatedAt)}
          {conversation.messageCount > 0
            ? ` · ${conversation.messageCount} mensajes`
            : ""}
        </span>
      </span>
    </button>
  );
}

function EmptySearchState() {
  return (
    <div className="px-4 py-10 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent-light text-accent">
        <SearchIcon />
      </div>
      <p className="text-sm font-medium text-foreground">
        No encontramos conversaciones
      </p>
      <p className="mt-1 text-xs text-muted">Prueba con otra palabra del título.</p>
    </div>
  );
}

function SearchIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
    </svg>
  );
}

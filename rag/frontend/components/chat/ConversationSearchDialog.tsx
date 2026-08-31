"use client";

import { useRef, type RefObject } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Conversation } from "@/hooks/useConversations";
import { formatConversationDate } from "@/components/chat/conversationSidebarUtils";
import { useDialog } from "@/components/common/useDialog";

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

	// Usa la primitiva `useDialog` compartida en vez de un `useEffect`
	// local de Escape + foco inicial: mismo comportamiento (foco va al
	// campo de búsqueda, no al primer elemento focusable del panel, que
	// sería el botón de cerrar) vía `initialFocusRef`, y además contiene
	// el foco con Tab/Shift+Tab y lo restaura al disparador al cerrar.
	const { panelRef, titleId } = useDialog({
		open,
		onClose,
		initialFocusRef: inputRef,
	});

	return (
		<AnimatePresence>
			{open && (
				<motion.div
					className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 px-4 backdrop-blur-md"
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					exit={{ opacity: 0 }}
					transition={{ duration: 0.16 }}
					aria-hidden="false"
				>
					{/* Overlay de cierre por click-afuera: se usa `<div
					   aria-hidden>` (no `<button>`) para que quede fuera del orden de
					   tabulación, igual que el mismo patrón usado en FeedbackModal y
					   MessageRatingPopover — un usuario de teclado ya cierra este
					   diálogo con Escape (vía useDialog), así que este overlay de
					   pantalla completa no aporta nada por Tab y, como botón real,
					   quedaría enfocable sin ningún indicador visible al recibir foco. */}
					<div
						className="absolute inset-0 cursor-default"
						aria-hidden="true"
						onClick={onClose}
					/>
					<motion.div
						ref={panelRef}
						tabIndex={-1}
						role="dialog"
						aria-modal="true"
						aria-labelledby={titleId}
						data-conversation-search-dialog
						className="relative z-10 flex max-h-[72vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-border bg-elevated shadow-2xl shadow-secondary-turquoise/20"
						initial={{ opacity: 0, y: 18, scale: 0.98 }}
						animate={{ opacity: 1, y: 0, scale: 1 }}
						exit={{ opacity: 0, y: 10, scale: 0.98 }}
						transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
					>
						<SearchHeader
							titleId={titleId}
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
	titleId,
	inputRef,
	search,
	hasSearch,
	onSearchChange,
	onClose,
}: {
	titleId: string;
	inputRef: RefObject<HTMLInputElement | null>;
	search: string;
	hasSearch: boolean;
	onSearchChange: (value: string) => void;
	onClose: () => void;
}) {
	return (
		<div className="relative border-b border-border p-4">
			<button
				type="button"
				onClick={onClose}
				aria-label="Cerrar búsqueda"
				className="absolute right-4 top-4 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
			>
				<CloseIcon />
			</button>
			<div className="mb-3 text-center">
				<h2 id={titleId} className="text-xl font-semibold text-foreground">
					Buscar conversaciones
				</h2>
				<p className="mt-0.5 text-xs text-subtle">
					Encuentra una conversación por título y ábrela al instante.
				</p>
			</div>

			<label htmlFor="conversation-search-dialog" className="sr-only">
				Buscar conversaciones
			</label>
			<div className="flex items-center gap-3 rounded-full border border-border bg-surface px-4 py-2.5 transition-[border-color,box-shadow] duration-150 focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-soft)]">
				<SearchIcon className="shrink-0 text-subtle" />
				<input
					ref={inputRef}
					id="conversation-search-dialog"
					type="text"
					value={search}
					onChange={(event) => onSearchChange(event.target.value)}
					placeholder="Buscar conversaciones…"
					className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-subtle focus:outline-none"
				/>
				{hasSearch && (
					<button
						type="button"
						onClick={() => {
							onSearchChange("");
							inputRef.current?.focus();
						}}
						aria-label="Limpiar búsqueda"
						className="shrink-0 rounded-full px-2.5 py-1 text-xs font-medium text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
			<div className="px-3 py-2 text-[11px] font-medium text-subtle">
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
			className={`group flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
				active
					? "bg-surface text-foreground"
					: "text-muted hover:bg-surface hover:text-foreground"
			}`}
		>
			<span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface text-subtle transition-colors group-hover:bg-accent-soft group-hover:text-accent">
				<ChatIcon />
			</span>
			<span className="min-w-0 flex-1">
				<span className="block truncate text-sm font-medium">
					{conversation.title}
				</span>
				<span className="mt-0.5 block text-xs text-subtle">
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
			<div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
				<SearchIcon />
			</div>
			<p className="text-sm font-medium text-foreground">
				No encontramos conversaciones
			</p>
			<p className="mt-1 text-xs text-muted">
				Prueba con otra palabra del título.
			</p>
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

"use client";

import { useState, type ReactNode } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "@/components/providers/AuthProvider";
import { ConversationList } from "@/components/chat/ConversationList";
import { ConversationSearchDialog } from "@/components/chat/ConversationSearchDialog";
import { SidebarUserMenu } from "@/components/chat/SidebarUserMenu";
import { useDialog } from "@/components/common/useDialog";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  SIDEBAR_TRANSITION,
} from "@/components/chat/conversationSidebarUtils";
import type { Conversation } from "@/hooks/useConversations";

interface ConversationSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  /** A4 — ver `useConversations`: mensaje del último refresco fallido, con la última lista válida aún en `conversations`. */
  loadError?: string | null;
  /** Colapsado/expandido del riel de escritorio. Persistido; NO controla el panel móvil (ver `mobileOpen`). */
  isExpanded: boolean;
  /**
   * Abierto/cerrado del panel off-canvas móvil. Deliberadamente
   * independiente de `isExpanded` (que persiste la preferencia de
   * colapso del riel de escritorio en localStorage): el panel móvil
   * siempre arranca cerrado y no comparte ese booleano persistido.
   */
  mobileOpen: boolean;
  transitionEnabled: boolean;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onNewChat: () => void;
  /** Alterna el panel relevante para el viewport actual (riel de escritorio o panel móvil). */
  onToggleSidebar: () => void;
  /** Cierra específicamente el panel móvil (backdrop, botón de cierre, Escape). */
  onCloseMobile: () => void;
  /**
   * Notifica al padre (`ChatInterface`) cuando el panel móvil termina por
   * completo su animación de salida — nunca antes. El padre la usa para
   * soltar el `inert` que mantiene bloqueada el área principal del chat
   * mientras el panel sigue montado y visible (ver "presencia modal",
   * `mobilePresent`, más abajo). Opcional: los consumidores que no
   * necesiten `inert` (p. ej. pruebas) pueden omitirla.
   */
  onMobileExitComplete?: () => void;
  /**
   * Refresca el listado de conversaciones (p. ej. tras renombrar o eliminar
   * una conversación). Es obligatorio: sin esta prop, ConversationList no
   * tiene forma de avisarle al padre que debe volver a pedir el listado, y
   * el sidebar queda mostrando datos obsoletos hasta que se recarga la
   * página.
   */
  onConversationsRefresh: () => Promise<void>;
}

export function ConversationSidebar({
  conversations,
  activeConversationId,
  loading,
  loadError = null,
  isExpanded,
  mobileOpen,
  transitionEnabled,
  onSelectConversation,
  onNewChat,
  onToggleSidebar,
  onCloseMobile,
  onMobileExitComplete,
  onConversationsRefresh,
}: ConversationSidebarProps) {
  const { user, role, signOut } = useAuth();
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  // Recuerda que la búsqueda debe abrirse en cuanto el panel móvil
  // termine de salir (ver `openSearch` y `handleMobileExitComplete` más
  // abajo): mientras `MobileSidebar` sigue animando su salida, su nodo
  // `role="dialog" aria-modal="true"` sigue montado, así que abrir la
  // búsqueda de inmediato dejaría dos diálogos modales coexistiendo.
  const [pendingMobileSearch, setPendingMobileSearch] = useState(false);
  // "Presencia modal" del panel móvil: a diferencia de `mobileOpen` (que
  // solo indica si el panel está entrando o saliendo), esta bandera sigue
  // en `true` durante toda la animación de salida y solo baja a `false`
  // cuando `handleMobileExitComplete` confirma que ya terminó. La usa
  // `MobileSidebar` para mantener activo `useDialog` (atrapado de Tab,
  // retorno de foco recién al terminar) mientras el panel sigue visible, y
  // este componente la reenvía a `ChatInterface` (vía
  // `onMobileExitComplete`) para que mantenga el área principal del chat
  // con `inert` durante ese mismo tramo.
  const [mobilePresent, setMobilePresent] = useState(mobileOpen);
  const isAdmin = role === "admin" || role === "super-admin";

  const searchResults = conversations.filter((conversation) =>
    (conversation.title ?? "").toLowerCase().includes(search.toLowerCase())
  );
  const hasSearch = search.trim().length > 0;
  const userInfo = getUserInfo(user);

  // Si el panel móvil vuelve a abrirse antes de que termine de salir (p.
  // ej. el usuario lo reabre mientras una búsqueda pospuesta todavía
  // espera `handleMobileExitComplete`), esa apertura pendiente ya no
  // corresponde: se cancela. Se ajusta durante el render, comparando con
  // el valor anterior guardado en estado (no en una ref: React no permite
  // leer `ref.current` durante el render), y solo se llama a `setState`
  // cuando la comparación detecta un cambio real: es el patrón que React
  // recomienda para reaccionar a un cambio de prop sin la renderización en
  // cascada extra que provocaría hacerlo en un `useEffect` (ver
  // "Adjusting some state when a prop changes" en la documentación de
  // React).
  const [prevMobileOpen, setPrevMobileOpen] = useState(mobileOpen);
  if (mobileOpen !== prevMobileOpen) {
    setPrevMobileOpen(mobileOpen);
    if (mobileOpen) {
      // El panel vuelve a entrar: su presencia se activa de inmediato (no
      // hay que esperar ninguna animación para empezar a bloquear el
      // fondo). Cualquier búsqueda pospuesta de una salida anterior ya no
      // corresponde.
      setMobilePresent(true);
      if (pendingMobileSearch) {
        setPendingMobileSearch(false);
      }
    }
  }

  function closePanels() {
    setSearchOpen(false);
    setProfileOpen(false);
    setPendingMobileSearch(false);
  }

  function handleNewChat() {
    closePanels();
    onNewChat();
  }

  function handleToggleSidebar() {
    closePanels();
    onToggleSidebar();
  }

  // Única salida del panel móvil (backdrop, botón "×" del encabezado y
  // Escape vía `useDialog`); separada de `handleToggleSidebar`, que además
  // sirve para *abrir* el riel de escritorio y no debe reutilizarse aquí.
  function closeMobilePanel() {
    closePanels();
    onCloseMobile();
  }

  function openSearch() {
    setProfileOpen(false);
    // El disparador puede ser tanto el propio panel móvil como el riel
    // de escritorio (comparten esta función). Si el panel móvil está
    // abierto, su nodo `role="dialog" aria-modal="true"` sigue montado
    // mientras `AnimatePresence` anima la salida: abrir la búsqueda de
    // inmediato dejaría, durante esa animación, dos diálogos modales
    // coexistiendo en el documento. Se pospone la apertura hasta que
    // `handleMobileExitComplete` confirme que el panel ya terminó de
    // salir.
    if (mobileOpen) {
      setPendingMobileSearch(true);
      onCloseMobile();
      return;
    }
    setSearchOpen(true);
  }

  // Conectado directamente a `AnimatePresence.onExitComplete` dentro de
  // `MobileSidebar`: se dispara una única vez, cuando el panel móvil y su
  // backdrop (ambos dentro del mismo `AnimatePresence` ahora) terminaron
  // por completo su animación de salida (nunca durante ella). Libera la
  // presencia modal — con lo que `useDialog` en `MobileSidebar` suelta el
  // foco hacia el disparador, y `ChatInterface`, vía
  // `onMobileExitComplete`, suelta el `inert` del área principal — y, si
  // había una búsqueda pospuesta, recién ahí la abre: así se garantiza que
  // el diálogo del panel ya no existe en el documento antes de montar el
  // de búsqueda.
  function handleMobileExitComplete() {
    setMobilePresent(false);
    onMobileExitComplete?.();
    if (pendingMobileSearch) {
      setPendingMobileSearch(false);
      setSearchOpen(true);
    }
  }

  async function handleSelectConversation(conv: Conversation) {
    closePanels();
    await onSelectConversation(conv);
  }

  async function handleSignOut() {
    setProfileOpen(false);
    await signOut();
  }

  return (
    <>
      <DesktopSidebar
        expanded={isExpanded}
        transitionEnabled={transitionEnabled}
        hasSearch={hasSearch}
        profileOpen={profileOpen}
        userInfo={userInfo}
        isAdmin={isAdmin}
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={loading}
        loadError={loadError}
        onToggleSidebar={handleToggleSidebar}
        onNewChat={handleNewChat}
        onOpenSearch={openSearch}
        onCollapsedSearch={openSearch}
        onToggleProfile={() => {
          setSearchOpen(false);
          setProfileOpen((current) => !current);
        }}
        onCloseProfile={() => setProfileOpen(false)}
        onSignOut={handleSignOut}
        onSelectConversation={handleSelectConversation}
        onConversationsRefresh={onConversationsRefresh}
      />

      <MobileSidebar
        open={mobileOpen}
        present={mobilePresent}
        onExitComplete={handleMobileExitComplete}
        hasSearch={hasSearch}
        profileOpen={profileOpen}
        userInfo={userInfo}
        isAdmin={isAdmin}
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={loading}
        loadError={loadError}
        onToggleSidebar={closeMobilePanel}
        onNewChat={handleNewChat}
        onOpenSearch={openSearch}
        onToggleProfile={() => {
          setSearchOpen(false);
          setProfileOpen((current) => !current);
        }}
        onCloseProfile={() => setProfileOpen(false)}
        onSignOut={handleSignOut}
        onSelectConversation={handleSelectConversation}
        onConversationsRefresh={onConversationsRefresh}
      />

      <ConversationSearchDialog
        open={searchOpen}
        search={search}
        conversations={conversations}
        results={searchResults}
        activeConversationId={activeConversationId}
        loading={loading}
        onSearchChange={setSearch}
        onClose={() => setSearchOpen(false)}
        onSelectConversation={handleSelectConversation}
      />
    </>
  );
}

interface SidebarContentProps {
  hasSearch: boolean;
  profileOpen: boolean;
  userInfo: UserInfo;
  isAdmin: boolean;
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  loadError?: string | null;
  onToggleSidebar: () => void;
  onNewChat: () => void;
  onOpenSearch: () => void;
  onToggleProfile: () => void;
  onCloseProfile: () => void;
  onSignOut: () => Promise<void>;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onConversationsRefresh: () => Promise<void>;
}

function DesktopSidebar({
  expanded,
  transitionEnabled,
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  loadError,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onCollapsedSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
  onConversationsRefresh,
}: SidebarContentProps & {
  expanded: boolean;
  transitionEnabled: boolean;
  onCollapsedSearch: () => void;
}) {
  return (
    <motion.aside
      className={`hidden flex-none overflow-visible md:flex md:flex-col ${
        expanded
          ? "border-r border-border bg-elevated/60 backdrop-blur-md"
          : "bg-transparent"
      }`}
      initial={false}
      animate={{
        width: expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH,
      }}
      transition={transitionEnabled ? SIDEBAR_TRANSITION : { duration: 0 }}
      aria-label={expanded ? "Historial de conversaciones" : "Panel de conversaciones"}
    >
      <AnimatePresence mode="wait" initial={false}>
        {expanded ? (
          <motion.div
            key="expanded"
            className="flex h-full min-w-0 flex-col overflow-hidden"
            initial={transitionEnabled ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: transitionEnabled ? 0.12 : 0 }}
          >
            <ExpandedSidebarContent
              hasSearch={hasSearch}
              profileOpen={profileOpen}
              userInfo={userInfo}
              isAdmin={isAdmin}
              conversations={conversations}
              activeConversationId={activeConversationId}
              loading={loading}
              loadError={loadError}
              onToggleSidebar={onToggleSidebar}
              onNewChat={onNewChat}
              onOpenSearch={onOpenSearch}
              onToggleProfile={onToggleProfile}
              onCloseProfile={onCloseProfile}
              onSignOut={onSignOut}
              onSelectConversation={onSelectConversation}
              onConversationsRefresh={onConversationsRefresh}
            />
          </motion.div>
        ) : (
          <CollapsedSidebarContent
            hasSearch={hasSearch}
            profileOpen={profileOpen}
            userInfo={userInfo}
            isAdmin={isAdmin}
            onToggleSidebar={onToggleSidebar}
            onNewChat={onNewChat}
            onOpenSearch={onCollapsedSearch}
            onToggleProfile={onToggleProfile}
            onCloseProfile={onCloseProfile}
            onSignOut={onSignOut}
            transitionEnabled={transitionEnabled}
          />
        )}
      </AnimatePresence>
    </motion.aside>
  );
}

function MobileSidebar({
  open,
  present,
  onExitComplete,
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  loadError,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
  onConversationsRefresh,
}: SidebarContentProps & {
  open: boolean;
  /**
   * "Presencia modal": sigue en `true` mientras el panel sigue montado
   * saliendo, no solo mientras `open` es `true`. Ver el estado homónimo en
   * `ConversationSidebar`.
   */
  present: boolean;
  onExitComplete: () => void;
}) {
  // El panel móvil es un overlay a pantalla completa sobre el resto de la
  // app (con backdrop propio): a diferencia del popover de citas no modal
  // (ver AssistantBubble), aquí sí corresponde atrapar el foco con Tab
  // mientras está abierto y devolverlo al disparador (el botón de
  // hamburguesa del header) al cerrar. `onToggleSidebar` para esta
  // instancia siempre significa "cerrar": el padre (`ConversationSidebar`)
  // le pasa `closeMobilePanel`, la misma función que usan el backdrop y
  // el botón "×" del encabezado. El único overlay anidado que persiste
  // dentro de este panel es el menú de perfil (`SidebarUserMenu`, con su
  // propio listener de Escape independiente, sin pasar por `useDialog`):
  // `closeBlocked` evita que ESTE `useDialog` dispare también su propio
  // `onClose` por Escape mientras el menú de perfil sigue abierto encima
  // — la misma pulsación primero cierra el menú (listener propio de
  // `SidebarUserMenu`); una segunda pulsación, ya sin overlay anidado,
  // cierra el panel móvil con normalidad. `closeBlocked` no toca el
  // atrapado de Tab (que solo le concierne al enfoque, no al cierre).
  // `open` (arriba) solo controla si el panel está entrando o saliendo —
  // es la señal que `AnimatePresence` necesita para arrancar su propia
  // animación de salida. `useDialog` en cambio recibe `present`: sigue
  // activo (atrapa Tab, escucha Escape) mientras el panel sigue montado
  // saliendo, y solo suelta el foco hacia el disparador cuando la
  // presencia baja a `false` (en `handleMobileExitComplete`, ya con el
  // panel fuera del documento).
  const { panelRef } = useDialog({
    open: present,
    onClose: onToggleSidebar,
    closeBlocked: profileOpen,
  });

  return (
    // `onExitComplete` reenvía directamente el callback del padre: se
    // dispara cuando el backdrop y el panel —ambos dentro de este mismo
    // `AnimatePresence`, así que permanecen montados juntos durante toda
    // la salida— terminan por completo su animación, momento en el que el
    // componente padre puede soltar la presencia modal y abrir con
    // seguridad el diálogo de búsqueda si había una apertura pospuesta
    // (ver `openSearch`/`handleMobileExitComplete` en ConversationSidebar).
    <AnimatePresence onExitComplete={onExitComplete}>
      {open && (
        <motion.div
          key="mobile-sidebar-backdrop"
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={onToggleSidebar}
          aria-hidden="true"
          // Sin fade propio: `exit` aquí solo sirve para que
          // `AnimatePresence` lo mantenga montado (requisito suyo para
          // diferir el desmontaje) hasta que el panel también termine, sin
          // cambiar la apariencia del backdrop.
          exit={{ opacity: 1 }}
          transition={SIDEBAR_TRANSITION}
        />
      )}
      {open && (
        <motion.aside
          key="mobile-sidebar-panel"
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label="Historial de conversaciones"
          className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface md:hidden"
          initial={{ x: -264 }}
          animate={{ x: 0 }}
          exit={{ x: -264 }}
          transition={SIDEBAR_TRANSITION}
        >
          <ExpandedSidebarContent
            hasSearch={hasSearch}
            profileOpen={profileOpen}
            userInfo={userInfo}
            isAdmin={isAdmin}
            conversations={conversations}
            activeConversationId={activeConversationId}
            loading={loading}
            loadError={loadError}
            onToggleSidebar={onToggleSidebar}
            onNewChat={onNewChat}
            onOpenSearch={onOpenSearch}
            onToggleProfile={onToggleProfile}
            onCloseProfile={onCloseProfile}
            onSignOut={onSignOut}
            onSelectConversation={onSelectConversation}
            onConversationsRefresh={onConversationsRefresh}
          />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function ExpandedSidebarContent({
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  loadError,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
  onConversationsRefresh,
}: SidebarContentProps) {
  const router = useRouter();
  const hasConversations = conversations.length > 0;
  return (
    <>
      <SidebarHeader onToggleSidebar={onToggleSidebar} />

      <div className="px-3 pt-2">
        <SidebarPillButton
          label="Nueva consulta"
          icon={<PencilEditIcon />}
          emphasis="primary"
          onClick={onNewChat}
        />
        <SidebarPillButton
          label="Buscar conversaciones"
          icon={<SearchIcon />}
          emphasis={hasSearch ? "active" : "default"}
          onClick={onOpenSearch}
        />
        <SidebarPillButton
          label="Cómo funciona"
          icon={<InfoIcon />}
          onClick={() => router.push("/about")}
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {(hasConversations || loading) && (
          <p className="px-5 pb-1 pt-5 text-[11px] font-medium text-subtle">
            Recientes
          </p>
        )}
        <ConversationList
          conversations={conversations}
          activeConversationId={activeConversationId}
          loading={loading}
          loadError={loadError}
          onRetryLoad={onConversationsRefresh}
          onSelectConversation={onSelectConversation}
          onNewChat={onNewChat}
          onConversationsRefresh={onConversationsRefresh}
        />
      </div>

      <SidebarUserMenu
        expanded
        open={profileOpen}
        userName={userInfo.name}
        userEmail={userInfo.email}
        userInitial={userInfo.initial}
        isAdmin={isAdmin}
        onToggle={onToggleProfile}
        onClose={onCloseProfile}
        onSignOut={onSignOut}
      />
    </>
  );
}

function CollapsedSidebarContent({
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  transitionEnabled,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
}: Pick<SidebarContentProps, "hasSearch" | "profileOpen" | "userInfo" | "isAdmin"> & {
  transitionEnabled: boolean;
  onToggleSidebar: () => void;
  onNewChat: () => void;
  onOpenSearch: () => void;
  onToggleProfile: () => void;
  onCloseProfile: () => void;
  onSignOut: () => Promise<void>;
}) {
  const router = useRouter();
  return (
    <motion.div
      key="collapsed"
      className="flex h-full flex-col items-center gap-2 px-2 pt-3"
      initial={transitionEnabled ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: transitionEnabled ? 0.12 : 0 }}
    >
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label="Abrir panel"
        title="Abrir panel"
        className="group/atlas relative mb-2 flex h-12 w-12 items-center justify-center rounded-full text-foreground transition-colors duration-150 hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className="absolute inset-0 flex items-center justify-center transition-opacity duration-150 group-hover/atlas:opacity-0 group-focus-visible/atlas:opacity-0">
          <AtlasGlyph />
        </span>
        <span className="absolute inset-0 flex items-center justify-center text-muted opacity-0 transition-opacity duration-150 group-hover/atlas:opacity-100 group-hover/atlas:text-foreground group-focus-visible/atlas:opacity-100 group-focus-visible/atlas:text-foreground">
          <PanelIcon />
        </span>
      </button>
      <RailButton
        label="Nueva consulta"
        icon={<PlusIcon />}
        onClick={onNewChat}
      />
      <RailButton
        label="Buscar conversaciones"
        icon={<SearchIcon />}
        active={hasSearch}
        onClick={onOpenSearch}
      />
      <RailButton
        label="Cómo funciona"
        icon={<InfoIcon />}
        onClick={() => router.push("/about")}
      />

      <div className="mt-auto pb-2">
        <SidebarUserMenu
          expanded={false}
          open={profileOpen}
          userName={userInfo.name}
          userEmail={userInfo.email}
          userInitial={userInfo.initial}
          isAdmin={isAdmin}
          onToggle={onToggleProfile}
          onClose={onCloseProfile}
          onSignOut={onSignOut}
        />
      </div>
    </motion.div>
  );
}

export function AtlasGlyph() {
  return (
    <Image
      src="/brand/atlas-icon.png"
      alt=""
      width={32}
      height={32}
      className="shrink-0 rounded-full"
      priority
    />
  );
}

function SidebarHeader({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  return (
    <div className="flex h-14 items-center justify-between px-5">
      <div className="flex items-center gap-2.5">
        <AtlasGlyph />
        <span
          className="text-base font-medium tracking-[0.04em] text-foreground"
          translate="no"
        >
          ATLAS
        </span>
      </div>
      <button
        onClick={onToggleSidebar}
        aria-label="Cerrar panel"
        title="Cerrar panel"
        className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <PanelIcon />
      </button>
    </div>
  );
}

export function SidebarPillButton({
  label,
  icon,
  emphasis = "default",
  onClick,
}: {
  label: string;
  icon: ReactNode;
  emphasis?: "default" | "primary" | "active";
  onClick: () => void;
}) {
  const emphasisClasses =
    emphasis === "primary"
      ? "bg-elevated text-foreground hover:bg-surface"
      : emphasis === "active"
        ? "bg-accent-soft text-accent"
        : "text-muted hover:bg-elevated hover:text-foreground";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`mt-1 flex w-full items-center gap-3 rounded-full px-4 py-3 text-[14.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${emphasisClasses}`}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  );
}

export function RailButton({
  label,
  icon,
  active = false,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`flex h-12 w-12 items-center justify-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
        active
          ? "bg-accent-soft text-accent"
          : "text-muted hover:bg-elevated hover:text-foreground"
      }`}
    >
      {icon}
    </button>
  );
}

interface UserInfo {
  email: string;
  name: string;
  initial: string;
}

function getUserInfo(user: ReturnType<typeof useAuth>["user"]): UserInfo {
  const email = user?.email ?? "usuario@correo.com";
  const name = user?.display_name ?? email.split("@")[0] ?? "Usuario";
  return {
    email,
    name,
    initial: name[0]?.toUpperCase() ?? "U",
  };
}

export function PanelIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

export function PlusIcon() {
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
      className="shrink-0"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  );
}

export function InfoIcon() {
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
      className="shrink-0"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}

export function PencilEditIcon() {
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
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

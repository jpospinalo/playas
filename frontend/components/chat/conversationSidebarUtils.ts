export const SIDEBAR_EXPANDED_WIDTH = 272;
export const SIDEBAR_COLLAPSED_WIDTH = 56;
export const SIDEBAR_TRANSITION = {
  duration: 0.22,
  ease: [0.16, 1, 0.3, 1],
} as const;

export function formatConversationDate(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / 86_400_000);

  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  if (days < 7) return `Hace ${days} días`;

  return date.toLocaleDateString("es-CO", {
    day: "numeric",
    month: "short",
  });
}

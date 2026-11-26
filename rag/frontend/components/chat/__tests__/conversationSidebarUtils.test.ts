import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatConversationDate } from "@/components/chat/conversationSidebarUtils";

const NOW = new Date("2026-11-23T00:00:00.000Z");
const DAY = 86_400_000;

function absoluteDate(date: Date): string {
  return new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "short",
  }).format(date);
}

describe("formatConversationDate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it.each([
    ["el instante actual", 0, "Hoy"],
    ["un milisegundo transcurrido", 1, "Hoy"],
    ["menos de 24 horas", DAY - 1, "Hoy"],
    ["exactamente 24 horas", DAY, "Ayer"],
    ["menos de 48 horas", 2 * DAY - 1, "Ayer"],
    ["exactamente 48 horas", 2 * DAY, "Hace 2 días"],
    ["menos de siete días", 7 * DAY - 1, "Hace 6 días"],
  ])("conserva la etiqueta para %s", (_, elapsed, expected) => {
    expect(formatConversationDate(new Date(NOW.getTime() - elapsed))).toBe(expected);
  });

  it.each([7, 14])("conserva la fecha absoluta desde %i días", (days) => {
    const date = new Date(NOW.getTime() - days * DAY);
    expect(formatConversationDate(date)).toBe(absoluteDate(date));
  });

  it.each([
    ["un milisegundo", 1],
    ["cinco horas", 5 * 60 * 60 * 1000],
    ["un año", 365 * DAY],
  ])("muestra una fecha absoluta si está %s en el futuro", (_, ahead) => {
    const date = new Date(NOW.getTime() + ahead);
    expect(formatConversationDate(date)).toBe(absoluteDate(date));
  });

  it("muestra una alternativa legible para una fecha inválida", () => {
    expect(formatConversationDate(new Date(Number.NaN))).toBe("Fecha no disponible");
  });

  it.each([
    ["2026-11-23T00:00:00.000Z", "2026-11-22T19:00:00.000-05:00", "Hoy"],
    ["2026-11-22T00:00:00.000Z", "2026-11-21T19:00:00.000-05:00", "Ayer"],
    ["2026-11-21T00:00:00.000Z", "2026-11-20T19:00:00.000-05:00", "Hace 2 días"],
  ])("respeta el mismo instante expresado como %s y UTC-5", (utc, colombia, expected) => {
    expect(formatConversationDate(new Date(utc))).toBe(expected);
    expect(formatConversationDate(new Date(colombia))).toBe(expected);
  });
});

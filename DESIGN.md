---
name: ATLAS
description: Asistente conversacional que traduce jurisprudencia colombiana sobre playas y derecho costero a respuestas comprensibles para ciudadanos sin formación legal
colors:
  abyss-bg: "oklch(8% 0.02 220)"
  abyss-surface: "oklch(12% 0.025 220)"
  abyss-elevated: "oklch(16% 0.028 220)"
  abyss-border: "oklch(22% 0.02 220)"
  abyss-border-strong: "oklch(32% 0.025 220)"
  abyss-fg: "oklch(96% 0.005 200)"
  abyss-fg-muted: "oklch(68% 0.015 210)"
  abyss-fg-subtle: "oklch(48% 0.018 215)"
  shore-bg: "oklch(98.5% 0.005 200)"
  shore-surface: "oklch(100% 0 0)"
  shore-elevated: "oklch(99% 0.003 200)"
  shore-border: "oklch(90% 0.008 210)"
  shore-border-strong: "oklch(78% 0.012 210)"
  shore-fg: "oklch(18% 0.025 220)"
  shore-fg-muted: "oklch(44% 0.018 215)"
  shore-fg-subtle: "oklch(60% 0.015 210)"
  glow-core: "oklch(72% 0.18 180)"
  glow-mid: "oklch(58% 0.16 185)"
  glow-edge: "oklch(40% 0.12 195)"
  glow-halo-light: "oklch(85% 0.08 180)"
  accent: "oklch(72% 0.18 180)"
  accent-hover: "oklch(78% 0.18 180)"
  accent-fg: "oklch(10% 0.02 220)"
  accent-soft: "oklch(72% 0.18 180 / 12%)"
  accent-light: "oklch(48% 0.18 185)"
  accent-light-hover: "oklch(42% 0.18 185)"
  accent-light-fg: "oklch(99% 0.003 200)"
  cite-bg: "oklch(72% 0.18 180 / 10%)"
  cite-fg: "oklch(72% 0.18 180)"
  cite-bg-light: "oklch(48% 0.18 185 / 8%)"
  cite-fg-light: "oklch(38% 0.18 188)"
  danger: "oklch(62% 0.18 25)"
  warn: "oklch(72% 0.14 75)"
  success: "oklch(64% 0.14 155)"
typography:
  display:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "clamp(2.25rem, 5.5vw, 3.75rem)"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  hero:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 4vw, 2.625rem)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.7
  small:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Geist, Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.02em"
  mono:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0px"
  sm: "6px"
  md: "10px"
  lg: "16px"
  xl: "24px"
  full: "9999px"
spacing:
  px: "1px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  base: "16px"
  lg: "24px"
  xl: "40px"
  2xl: "64px"
  3xl: "96px"
  4xl: "128px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.full}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.full}"
    padding: "10px 20px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.abyss-fg-muted}"
    rounded: "{rounded.full}"
    padding: "10px 16px"
  button-icon:
    backgroundColor: "transparent"
    textColor: "{colors.abyss-fg-muted}"
    rounded: "{rounded.full}"
    padding: "8px"
  input-chat:
    backgroundColor: "{colors.abyss-surface}"
    textColor: "{colors.abyss-fg}"
    rounded: "{rounded.xl}"
    padding: "14px 20px"
  badge-citation:
    backgroundColor: "{colors.cite-bg}"
    textColor: "{colors.cite-fg}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  seed-chip:
    backgroundColor: "transparent"
    textColor: "{colors.abyss-fg-muted}"
    rounded: "{rounded.full}"
    padding: "8px 14px"
  message-user:
    backgroundColor: "{colors.abyss-elevated}"
    textColor: "{colors.abyss-fg}"
    rounded: "{rounded.lg}"
    padding: "12px 16px"
  popover-source:
    backgroundColor: "{colors.abyss-elevated}"
    textColor: "{colors.abyss-fg}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: ATLAS

## 1. Overview

**Creative North Star: "Bioluminiscencia"**

ATLAS abandona por completo la identidad institucional-legal anterior (platino, azul de sello, serif clásico) y adopta una sola decisión visual fuerte que carga toda la personalidad: un glow ambiental bioluminiscente turquesa-verde, suspendido sobre un fondo casi negro de profundidad oceánica. El glow es la única licencia decorativa del sistema; todo lo demás es geometría limpia, tipografía sans contemporánea y espacio negativo generoso.

La referencia arquitectónica es la nueva UI de Google Gemini: sidebar de íconos flotantes (no panel sólido), input pill centrado, saludo personalizado en tipografía grande, espacio negativo enorme. ATLAS toma esa arquitectura y la diferencia con su propio gesto cromático — donde Gemini pone un glow índigo corporativo, ATLAS pone bioluminiscencia oceánica.

El sistema vive en **dark mode** y **light mode** con igual cuidado. En dark, el glow es protagonista — un halo radial intenso detrás del input y los momentos heroicos. En light, el glow se transforma en un halo turquesa muy sutil, casi una sombra de color que recuerda agua iluminada por sol. La arquitectura, tipografía y espaciado son idénticos en ambos modos; solo cambian los valores cromáticos.

**Características clave:**
- Una familia tipográfica única (Geist) en todo el sistema — sin serifs, sin mezclas
- Glow ambiental bioluminiscente como firma visual irreductible
- Sidebar de íconos flotantes, no paneles sólidos al estilo dashboard
- Pill shapes para inputs y botones de acción; cards solo cuando son la única respuesta correcta
- Citas como ciudadanos visuales de primera clase, pero subordinadas al contenido traducido
- Cero glassmorphism, cero gradient text, cero side-stripe borders, cero hero-metrics

## 2. Colors: Abyss & Bioluminescence

Dos familias de superficie (Abyss para dark, Shore para light) y una sola voz activa (Bioluminescent Glow) que se manifiesta como acento cromático y como halo ambiental. El sistema es deliberadamente monocromático con una sola intervención de color saturado.

### The Glow (firma del sistema)

- **Glow Core** (`oklch(72% 0.18 180)`): el centro del halo radial. Turquesa-verde brillante, evocación directa de fitoplancton bioluminiscente. Es el color del acento en dark mode y la fuente del halo ambiental.
- **Glow Mid** (`oklch(58% 0.16 185)`): el estrato medio del gradiente radial. Más profundo, más verde.
- **Glow Edge** (`oklch(40% 0.12 195)`): el borde del halo donde se desvanece hacia el fondo. Más azul, más oscuro.
- **Glow Halo Light** (`oklch(85% 0.08 180)`): la versión sutil del glow en light mode. Apenas perceptible, recuerda agua iluminada.

**Uso del glow ambiental:** se renderiza como un `radial-gradient` o `box-shadow` masivo (`blur` de 300–500px) detrás del input principal en el empty state y detrás del logo en momentos heroicos. Nunca en bordes de cards, nunca como decoración secundaria. Es **un solo gesto por pantalla**.

### Dark — Abyss

El dark mode es el modo de identidad de ATLAS. El fondo es casi negro pero deliberadamente azulado, evocación de mar nocturno profundo, no de pantalla de terminal.

- **Abyss BG** (`oklch(8% 0.02 220)`): fondo de aplicación. Muy oscuro, tinte azul-cian sutil.
- **Abyss Surface** (`oklch(12% 0.025 220)`): superficies elevadas mínimamente — input, popover.
- **Abyss Elevated** (`oklch(16% 0.028 220)`): mensajes del usuario, popovers de fuente.
- **Abyss Border** (`oklch(22% 0.02 220)`): bordes de 1px en superficies.
- **Abyss Border Strong** (`oklch(32% 0.025 220)`): bordes en estados activos o hover.
- **Abyss FG** (`oklch(96% 0.005 200)`): texto primario. Casi blanco con tinte cool muy leve.
- **Abyss FG Muted** (`oklch(68% 0.015 210)`): texto secundario, metadatos.
- **Abyss FG Subtle** (`oklch(48% 0.018 215)`): placeholder, deshabilitado, decorativo.

### Light — Shore

El light mode no es "dark mode invertido". Tiene su propia lógica: superficies casi blancas con un tinte cool muy sutil (no pergamino cálido, no platino frío del diseño anterior), tipografía muy oscura con tinte azul-cian (no negro puro), y el glow reducido a halo muy sutil de tipo agua-sol.

- **Shore BG** (`oklch(98.5% 0.005 200)`): fondo de aplicación. Casi blanco con tinte agua imperceptible.
- **Shore Surface** (`oklch(100% 0 0)`): superficies elevadas — input, mensajes.
- **Shore Elevated** (`oklch(99% 0.003 200)`): popovers, layers superiores.
- **Shore Border** (`oklch(90% 0.008 210)`): bordes de reposo.
- **Shore Border Strong** (`oklch(78% 0.012 210)`): bordes activos o hover.
- **Shore FG** (`oklch(18% 0.025 220)`): texto primario. Oscuro con tinte cool sutil.
- **Shore FG Muted** (`oklch(44% 0.018 215)`): texto secundario.
- **Shore FG Subtle** (`oklch(60% 0.015 210)`): placeholder, decorativo.

### Acento en light mode

El glow core (`oklch(72% 0.18 180)`) es brillante y se ve excelente sobre fondo oscuro, pero pierde legibilidad sobre fondos claros. En light mode, las acciones usan **Accent Light** (`oklch(48% 0.18 185)`) — el mismo hue, más profundo, para mantener contraste AA sobre Shore Surface.

- **Accent Light** (`oklch(48% 0.18 185)`): color de acento en light mode. Botones primarios, foco, links.
- **Accent Light Hover** (`oklch(42% 0.18 185)`): hover en light.
- **Accent Light FG** (`oklch(99% 0.003 200)`): texto sobre fondo accent en light.

### Citas — Cite Tokens

Las citas son el segundo elemento visual nombrado del sistema. En lugar de un color separado (como el charter amber del diseño anterior), las citas usan el mismo hue del acento pero con tratamiento de fondo translúcido. Esto las integra al sistema en vez de aislarlas como categoría aparte.

- **Cite BG** (`oklch(72% 0.18 180 / 10%)`): fondo translúcido del badge en dark.
- **Cite FG** (`oklch(72% 0.18 180)`): texto del badge en dark.
- **Cite BG Light** (`oklch(48% 0.18 185 / 8%)`): fondo en light.
- **Cite FG Light** (`oklch(38% 0.18 188)`): texto en light.

### Funcionales

- **Danger** (`oklch(62% 0.18 25)`): rojo coral, no rojo bombero. Solo errores reales.
- **Warn** (`oklch(72% 0.14 75)`): ámbar para advertencias suaves ("ATLAS no reemplaza un abogado").
- **Success** (`oklch(64% 0.14 155)`): verde apagado para confirmaciones. Casi nunca aparece.

### Named Rules

**One Glow Per View.** El glow ambiental aparece como protagonista máximo una vez por pantalla. En empty state, detrás del input. En conversación activa, no aparece (o aparece muy sutil detrás del logo). Multiplicar el glow lo convierte en decoración y mata su poder.

**Same Hue Discipline.** Acento, citas y glow usan el mismo hue (180–195). Cambia el chroma y la lightness; nunca el hue. Esto mantiene el sistema monocromático y cohesivo. Introducir otro hue saturado (rojo, púrpura, amarillo) requiere justificación funcional explícita.

**No Warm Surfaces.** Todos los fondos y superficies tienen tinte cool (hue 200–220). Cualquier superficie cálida (beige, crema, marfil) rompe la coherencia oceánica del sistema.

## 3. Typography

**Familia única:** Geist (variable, pesos 400/500/600/700) con fallback a Inter y system-ui. Geist Mono para identificadores de cita (números de expediente, fechas judiciales).

**Razón:** una sola familia mantiene la disciplina del sistema. Geist está diseñada para pantalla con excelente legibilidad en cuerpo pequeño y carácter suficiente en displays grandes. No es la fuente por defecto de "todo el mundo" (Inter), no es serif tradicional (que ya rechazamos), no es geométrica fría (Helvetica, Manrope). Es contemporánea sin ser tendencia.

### Jerarquía

- **Display** (Geist 500, clamp 2.25→3.75rem, lh 1.1, ls -0.025em): saludo en empty state ("Hola, ¿en qué te ayudo hoy?"), titulares de marca. Una vez por pantalla, máximo.
- **Hero** (Geist 500, clamp 1.75→2.625rem, lh 1.15, ls -0.02em): titulares de página secundaria (/about), heros de modal grandes.
- **Headline** (Geist 600, 1.375rem, lh 1.3): secciones dentro de una respuesta larga ("¿Qué puedes hacer?", "Fuentes"), títulos de modal.
- **Title** (Geist 600, 1rem, lh 1.4): títulos de conversación en sidebar, nombres de documento, encabezados de popover.
- **Body** (Geist 400, 0.9375rem, lh 1.7): texto de respuesta del asistente, mensajes del usuario. Línea máxima **68ch**.
- **Small** (Geist 400, 0.8125rem, lh 1.5): metadatos, timestamps, descripciones secundarias.
- **Label** (Geist 500, 0.75rem, ls 0.02em): chips, badges, etiquetas funcionales. Casi nunca uppercase.
- **Mono** (Geist Mono 400, 0.8125rem): números de expediente, fechas judiciales formateadas, identificadores técnicos en popover de fuente.

### Named Rules

**The 68ch Rule.** El cuerpo de la respuesta del asistente nunca supera 68ch. Las respuestas legales son densas; respetar el límite es respetar al lector.

**One Family, No Exceptions.** Geist en todo. Si aparece otra familia es porque alguien la importó sin pensar — quitarla. Geist Mono es Geist; cuenta como una sola familia.

**No Uppercase Long Strings.** Mayúsculas solo en labels de ≤2 palabras (ej: "FUENTES"). Cualquier frase en mayúsculas es ruido tipográfico.

## 4. Elevation & Depth

ATLAS usa principalmente **luz** (el glow) y **valor de superficie** como mecanismos de profundidad, no sombras. Las sombras existen pero son discretas y solo aparecen en respuesta a estado (popover abierto, hover en elemento elevable).

### Glow ambiental (no es sombra, es la firma)

```css
/* Dark mode, detrás del input en empty state */
background: radial-gradient(
  ellipse at center,
  oklch(72% 0.18 180 / 0.25) 0%,
  oklch(58% 0.16 185 / 0.15) 30%,
  oklch(40% 0.12 195 / 0.05) 60%,
  transparent 80%
);
filter: blur(60px);
```

En light mode el glow se atenúa a ~8% de opacidad y blur mayor — apenas un halo de tinte agua.

### Sombras

- **Lift** (dark): `0 8px 32px oklch(0% 0 0 / 0.4), 0 2px 8px oklch(0% 0 0 / 0.3)` — popovers de fuente, dropdowns.
- **Lift** (light): `0 8px 32px oklch(30% 0.02 220 / 0.08), 0 2px 8px oklch(30% 0.02 220 / 0.05)`.
- **Focus ring** (dark): `0 0 0 2px {abyss-bg}, 0 0 0 4px {accent}` — anillo doble para visibilidad sobre cualquier fondo.
- **Focus ring** (light): `0 0 0 2px {shore-bg}, 0 0 0 4px {accent-light}`.

### Named Rules

**Flat By Default.** Cards, sidebars, mensajes — flat al reposo. Las sombras aparecen cuando un elemento se despega de la superficie (popover abierto, modal flotante, dropdown). Una card no tiene sombra "porque es card".

**The Glow Is Not A Shadow.** No confundir el glow ambiental (decisión cromática) con sombras (mecánica de profundidad). El glow es luz, está siempre coloreado, está siempre detrás. Las sombras son neutras y reactivas.

## 5. Components

### Sidebar

Sidebar de íconos flotantes, no panel sólido. Vive sobre el fondo de la aplicación sin separarse con borde o sombra.

- **Ancho:** 64px desktop. Fondo transparente.
- **Contenido:** logo ATLAS arriba (sparkle/símbolo, ~28px), botones de íconos (nueva conversación, historial, configuración) alineados al centro vertical o agrupados arriba. Avatar abajo si está autenticado.
- **Hover en ícono:** fondo circular suave (Abyss Elevated / Shore Elevated), transición 150ms ease-out.
- **Activo:** color de ícono cambia a accent. Sin fondo, sin borde.
- **Click en historial:** abre panel temporal de conversaciones (ancho 280px, fondo Abyss Surface / Shore Surface, borde 1px en lado derecho). El panel es secundario al sidebar de íconos.
- **Mobile:** sidebar se vuelve off-canvas, se abre con botón hamburguesa en header mínimo.

### Empty State

La pantalla cuando el usuario entra sin conversación activa.

- **Layout:** flex column centrado verticalmente con sesgo ligero hacia arriba (40vh para el contenido, no 50%).
- **Saludo:** Display type, dinámico ("Buenas noches, Daniel" o "Hola, ¿en qué te ayudo hoy?"). Color Abyss FG / Shore FG. Sin glow detrás del texto.
- **Input principal:** pill shape, ancho máximo 720px, centrado. Glow ambiental masivo detrás (radial-gradient con blur 80px, opacidad 25% en dark / 8% en light).
- **Preguntas semilla:** 3–4 chips bajo el input, fila horizontal en desktop con flex-wrap, columna en mobile. Texto plano sobre transparente con borde sutil, padding `8px 14px`, rounded full. Click rellena el input, no envía.

### Chat Input

- **Forma:** pill (rounded `xl` = 24px o full según contexto), ancho contenido (`max-w-3xl ≈ 760px`) centrado horizontalmente.
- **Fondo:** Abyss Surface / Shore Surface. Borde 1px Abyss Border / Shore Border.
- **Padding:** 14px 20px texto, botón send 36×36 dentro del pill al lado derecho.
- **Focus:** borde cambia a Accent / Accent Light (1.5px). El glow ambiental detrás se intensifica ligeramente (no es animación, es estado).
- **Multiline:** crece hasta 8 líneas, luego scroll interno.
- **Send button:** ícono dentro del pill, círculo Accent al rellenar el input (deshabilitado opacity 40% cuando vacío).
- **Streaming:** mientras ATLAS responde, el glow pulsa lento (3s ease-in-out infinite). Bajo `prefers-reduced-motion`, sin pulso.

### Mensajes

- **Usuario:** alineado a la derecha, fondo Abyss Elevated / Shore Surface (con borde sutil en light), rounded lg, padding `12px 16px`, max-width 75% del contenedor.
- **ATLAS:** sin contenedor visual. Se renderiza directamente sobre el fondo, ancho completo del contenedor de chat. Estructura interna visible:
  - **TL;DR** (peso 500, color FG, 1–2 frases)
  - **Explicación** (body, color FG, párrafos prosa, máx 68ch)
  - **¿Qué puedes hacer?** (lista con dot leaders o números, verbos al inicio)
  - **Fuentes** (línea con label "Fuentes" pequeño + citas inline tipo badge)

### Badges de Cita

- **Forma:** pill rounded full, padding `2px 8px`, inline con baseline alignment.
- **Color:** Cite FG sobre Cite BG (10% del accent en dark, 8% en light).
- **Hover:** opacidad del fondo sube a 18%. Sin scale, sin shadow.
- **Focus visible:** anillo Accent / Accent Light de 2px con 2px offset.
- **Click:** abre popover de fuente inline (no modal, no nueva página).
- **Estado sin fuente disponible:** opacidad 40%, cursor not-allowed, tooltip "Fuente no disponible".

### Popover de Fuente

- **Contenedor:** Abyss Elevated / Shore Elevated, borde 1px Border, rounded lg, sombra Lift, padding 16px, max-width 380px.
- **Estructura:** Title (nombre de la sentencia), grid de metadatos (tribunal, fecha, expediente — Label + Small en dos columnas), separador (1px Border), excerpt (Body, max-height 12rem con scroll, line-clamp opcional), link al documento completo abajo (texto pequeño con flecha).
- **Triggered by:** click en badge de cita. Se posiciona above/below dependiendo del espacio. Se cierra al click fuera o ESC.

### Botones

- **Primario:** Accent BG, Accent FG, rounded full, padding `10px 20px`, peso 500. Hover: Accent Hover. No scale, no shadow.
- **Ghost:** transparente, FG Muted, rounded full, padding `10px 16px`. Hover: fondo Surface, FG.
- **Ícono:** transparente, 36×36 circular (rounded full), FG Muted. Hover: fondo Surface, FG.
- **Destructivo:** fondo transparente con borde 1px Danger, texto Danger. Hover: fondo Danger / 10%.

### Toggle de Tema

Tres opciones: claro / oscuro / system. Segmented control en sidebar (parte inferior) o en menú de configuración. Sin animación elaborada al cambiar — fade rápido de 200ms.

### Disclaimer Persistente

ATLAS no reemplaza un abogado. Aparece como texto pequeño (Small + FG Muted) bajo el input principal en el empty state, y como texto pequeño al pie de cada respuesta de ATLAS. Sin caja, sin ícono de warning, sin alarma visual — es información, no advertencia.

## 6. Do's and Don'ts

### Do:

- **Do** mantener el glow ambiental como única fuente de color saturado en cada pantalla. Un glow por vista, máximo.
- **Do** usar pill shapes para inputs y botones de acción. Reflejan la fluidez conversacional del producto.
- **Do** dejar respirar la respuesta del asistente. Sin contenedor, sin card, sobre el fondo directo.
- **Do** tratar las citas como elementos integrados al texto (badges inline) y como puntos de profundidad (popover expandible). Las dos cosas, no una.
- **Do** escribir copy en español llano. Si hay un término legal, definirlo al primer uso.
- **Do** respetar `prefers-reduced-motion` matando el pulso del glow durante streaming.
- **Do** asegurar contraste AA en ambos temas, incluyendo texto sobre el glow ambiental.
- **Do** mantener Geist como única familia. Si necesitas distinguir algo, usa peso o tamaño, no otra fuente.

### Don't:

- **Don't** poner glow en bordes de cards, en botones, en avatares, en ningún elemento que no sea el contenedor principal del momento. Se diluye y se vuelve decoración.
- **Don't** envolver la respuesta de ATLAS en una card o bubble. El asistente habla sobre la página, no desde una caja.
- **Don't** usar serif. Ni para títulos, ni para citas, ni para "darle elegancia". Geist hace todo el trabajo.
- **Don't** introducir hues saturados nuevos (rojo decorativo, púrpura de marca, amarillo de highlight). El sistema es monocromático: turquesa-verde + neutros + funcionales discretos.
- **Don't** copiar el azul-índigo de Gemini. La arquitectura sí, el color no.
- **Don't** poner side-stripe borders (>1px de color en lateral) en items de sidebar, en mensajes, en alertas. Prohibido por las leyes compartidas.
- **Don't** usar gradient text. El acento turquesa es distintivo por sí solo; no necesita degradado.
- **Don't** usar glassmorphism en superficies regulares. Backdrop blur solo en popovers sobre contenido scrollable, si acaso.
- **Don't** caer en el hero-metric template (big number + small label + icon grid) en /about o en el empty state. Cliché de SaaS.
- **Don't** usar warm neutrals (beige, crema, papel, marfil). Todos los neutros van con tinte cool — la familia anterior de "pergamino" se descarta.
- **Don't** mezclar el dark institucional anterior (`oklch(10% 0.025 260)`) con el nuevo Abyss. Son sistemas distintos; el viejo se descarta entero.
- **Don't** intentar imitar Gemini al pixel. La referencia es de arquitectura y energía, no de cromática ni de copy.

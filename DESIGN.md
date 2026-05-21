---
name: ATLAS
description: Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre playas en Colombia
colors:
  blue-institutional: "oklch(42% 0.14 258)"
  blue-bright: "oklch(48% 0.14 258)"
  blue-light: "oklch(42% 0.14 258 / 10%)"
  platinum-bg: "oklch(96.5% 0.004 260)"
  platinum-surface: "oklch(99% 0.002 260)"
  ink-deep: "oklch(10% 0.02 260)"
  ink-muted: "oklch(46% 0.012 260)"
  platinum-border: "oklch(86% 0.008 260)"
  platinum-subtle: "oklch(92% 0.006 260)"
  charter-amber: "oklch(52% 0.15 68)"
  charter-amber-fill: "oklch(52% 0.15 68 / 10%)"
  dark-institutional-bg: "oklch(10% 0.025 260)"
  dark-institutional-surface: "oklch(14% 0.03 260)"
  dark-blue-accent: "oklch(62% 0.16 258)"
  dark-ink-fg: "oklch(93% 0.005 80)"
  dark-ink-muted: "oklch(58% 0.015 260)"
  dark-institutional-border: "oklch(20% 0.03 260)"
typography:
  display:
    fontFamily: "EB Garamond, Georgia, serif"
    fontSize: "clamp(2rem, 5vw, 3.5rem)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "EB Garamond, Georgia, serif"
    fontSize: "clamp(1.4rem, 3vw, 2rem)"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.03em"
rounded:
  none: "0px"
  sm: "4px"
  md: "8px"
  lg: "12px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  2xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.blue-institutional}"
    textColor: "{colors.platinum-surface}"
    rounded: "{rounded.md}"
    padding: "10px 22px"
  button-primary-hover:
    backgroundColor: "{colors.blue-bright}"
    textColor: "{colors.platinum-surface}"
    rounded: "{rounded.md}"
    padding: "10px 22px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-deep}"
    rounded: "{rounded.md}"
    padding: "10px 22px"
  badge-citation:
    backgroundColor: "{colors.charter-amber-fill}"
    textColor: "{colors.charter-amber}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  input-chat:
    backgroundColor: "{colors.platinum-surface}"
    textColor: "{colors.ink-deep}"
    rounded: "{rounded.lg}"
    padding: "14px 16px"
---

# Design System: ATLAS

## 1. Overview

**Creative North Star: "Consejo"**

ATLAS is a professional legal instrument for Colombian lawyers. Its design system follows that function with no decoration: platinum-cold backgrounds that put zero visual noise between the lawyer and the text, a single institutional blue accent drawn from official Colombian government documents and court seals, and charter amber reserved exclusively for legal citations. The typography pairs a classical serif for ATLAS identity with Inter for every functional element. The result feels like a premium legal research system — authoritative, precise, enterprise-grade.

The primary surface is the conversation. Everything else is infrastructure. The sidebar, navigation, and chrome are subordinate — they exist to hold the exchange, not to compete with it. Dense legal text needs room to breathe and a typographic system that renders it legible, not a design system that competes with it.

Dark mode goes to deep institutional blue-black: `oklch(10% 0.025 260)` with near-white text and a brighter institutional blue accent. Both modes share the same structure — the tokens swap, the architecture stays.

**Key Characteristics:**
- Platinum-cold neutrals — near-colorless backgrounds that disappear behind the text
- Institutional blue (`oklch(40% 0.22 258)`) as the one active voice — precise, not corporate navy
- Charter Amber for citations only — legal sources are a first-class visual element
- EB Garamond for ATLAS identity and headings; Inter for all functional text
- Flat surfaces at rest; shadow only as a response to state
- Reduced motion respected globally; no gratuitous animation

## 2. Colors: The Institutional Palette

Two primary roles — platinum (neutral, near-colorless, background) and institutional blue (active, signal) — with charter amber reserved exclusively for legal citations.

### Primary

- **Institutional Blue** (`oklch(40% 0.22 258)`): The precise blue of Colombian official documents, court seals, and government entity stamps. Not navy — darker than navy has chroma; this is a precise measured blue. Used on primary buttons, send actions, interactive affordances, focus rings, and active sidebar states. Never used decoratively or as a background fill. Dark mode brightens to `oklch(62% 0.22 258)` for contrast on deep institutional dark.

- **Blue Bright** (`oklch(46% 0.22 258)`): Hover and active state. Same chroma, higher lightness. Never the resting color.

- **Blue Light** (`oklch(40% 0.22 258 / 10%)`): Translucent blue fill — used for selected/active chip backgrounds, shallow focus indicators. Not a text color.

### Secondary

- **Charter Amber** (`oklch(52% 0.15 68)`): Warm amber. Used **exclusively** for citation badges and their hover states. Never as a button color, never as a heading. This color means "source."

- **Charter Fill** (`oklch(52% 0.15 68 / 10%)`): The amber fill behind citation badges. Also used for blockquotes in rendered legal answers.

### Neutral

- **Platinum** (`oklch(96.5% 0.004 260)`): App background in light mode. Near-colorless with a barely perceptible cool tint. Not warm, not stark.
- **Document White** (`oklch(99% 0.002 260)`): Elevated surface — chat bubbles, cards, sidebar body. Near-pure white.
- **Institutional Ink** (`oklch(10% 0.02 260)`): Near-black for primary text. Deep cool undertone — the ink of official documents.
- **Faded Ink** (`oklch(46% 0.012 260)`): Secondary text, metadata, timestamps, placeholder text.
- **Platinum Border** (`oklch(86% 0.008 260)`): Borders and dividers. Cool, near-colorless.
- **Platinum Subtle** (`oklch(92% 0.006 260)`): Code blocks, subtle backgrounds.

**Dark mode token swap:** Background → `oklch(10% 0.025 260)`, Surface → `oklch(14% 0.03 260)`, Foreground → `oklch(93% 0.005 80)`, Muted → `oklch(58% 0.015 260)`, Border → `oklch(20% 0.03 260)`, Accent → `oklch(62% 0.22 258)`.

### Named Rules

**The Ink & Blue Rule.** Every interactive element uses institutional blue. Every resting surface is platinum or document white. These two families never blend — no blue backgrounds for content surfaces, no warm neutrals anywhere.

**The One Amber Rule.** Charter Amber appears only on citation badges and their hover states. If you are about to apply amber to anything else, stop. Choose blue or ink instead.

## 3. Typography

**Display Font:** EB Garamond (400, 500, 600, 700 — normal and italic), with Georgia, serif fallback

**Body Font:** Inter (400, 500, 600), with system-ui, sans-serif fallback

**Character:** EB Garamond anchors the ATLAS name and all structural headings in the tradition of cartographic atlases — authority earned through centuries of use, not decoration. Inter handles every functional element: navigation, inputs, metadata, body copy in the chat. The contrast between the two is the system's personality — scholarly identity, efficient instrument.

### Hierarchy

- **Display** (EB Garamond 500, clamp 2rem→3.5rem, lh 1.15, ls -0.01em): ATLAS wordmark and page-level titles. /about hero, empty state heading. Nowhere else.
- **Headline** (EB Garamond 500, clamp 1.4rem→2rem, lh 1.25, ls -0.005em): Section headings on /about, major structural titles in rendered answers. Use sparingly.
- **Title** (Inter 600, 1.0625rem, lh 1.3): Conversation titles in sidebar, modal headings, source document names.
- **Body** (Inter 400, 0.9375rem, lh 1.65): All rendered legal answer text. Max line length 68ch in full-width contexts. This is where lawyers spend their time — give it air.
- **Label** (Inter 500, 0.75rem, ls 0.03em): Timestamps, metadata chips, badge text, keyboard shortcuts. Uppercase sparingly, only for very short string (≤3 words).

### Named Rules

**The Two-Font Discipline.** EB Garamond is the name of the system. Inter is the voice of the system. Never mix them on the same semantic level — a heading is either Garamond or Inter, never both per role. Don't introduce a third font under any circumstance.

**The 68ch Rule.** Legal text rendered in assistant answers must never exceed 68ch. Wide justified blocks in dense prose are a usability failure, not a design choice.

## 4. Elevation

ATLAS uses tonal layering as its primary depth mechanism, not shadows. The background (`parchment`), surface (`paper`), and fog layers already communicate hierarchy through warmth and value. Shadows appear only in response to state — they are earned, not ambient.

### Shadow Vocabulary

- **Lift** (`0 2px 8px oklch(16% 0.02 55 / 0.10), 0 1px 2px oklch(16% 0.02 55 / 0.06)`): Applied to popovers, source tooltips, dropdowns. Communicates "this is above the surface" for transient layers.
- **Hover Glow** (`0 0 0 3px oklch(50% 0.13 196 / 0.18)`): Focus ring equivalent for interactive elements that use outline-based focus indicators. Not a shadow in the traditional sense — a teal halo.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. A card does not get a shadow because it's a card. A sidebar panel does not get a shadow because it's a sidebar. Shadows appear when an element detaches from the surface — on hover for interactive cards, on open for floating layers.

## 5. Components

### Buttons

Buttons in ATLAS are precise and contained. They don't shout. The primary button is the deepest teal; everything else steps back.

- **Shape:** Gently rounded (8px). Never pill-shaped, never square.
- **Primary:** Caribbean Depth background, Paper text, 10px 22px padding. Inter 500, 0.875rem.
- **Hover:** Caribbean Bright background. Transition 150ms ease-out. No scale transform.
- **Focus:** 3px Hover Glow ring (`oklch(50% 0.13 196 / 0.18)`), 2px offset.
- **Ghost:** Transparent background, Map Ink text. Hover: Fog background. Same shape and padding.
- **Icon button (send, etc.):** 36×36px, Caribbean Depth icon color at rest, Fog background on hover. No label.
- **Disabled:** 40% opacity across all variants. No pointer events.

### Citation Badges

The signature component of ATLAS. Legal sources are first-class visual elements.

- **Style:** Charter Fill background, Charter Amber text, 2px 8px padding, pill shape (9999px radius). Inter 500, 0.7em (relative to parent body text size). Inline, vertical-align baseline.
- **Hover:** Charter Amber fills to 18% opacity. Box shadow ring `0 0 0 2px` at 20% Charter Amber opacity.
- **Focus-visible:** 2px solid Charter Amber outline, 2px offset.
- **Missing source variant:** 38% opacity, pointer-events none. The badge renders but signals absence, not an error.

### Chat Bubbles

- **User message:** Right-aligned. Caribbean Depth background, Paper text. Rounded 12px, all corners. 14px 18px padding. Max-width 72%. Inter 400, body size.
- **Assistant message:** Left-aligned (or full-width). No background — renders directly on Parchment. Left-bounded prose. Uses `.rag-prose` typography classes. Source badges inline.
- **No "AI response bubble" container.** The assistant's answer is not wrapped in a card. It is the surface.

### Chat Input

- **Style:** Paper background, Stone border (1px), 12px radius. 14px 16px padding. Inter 400, body size. Full-width within a constrained container (max 760px centered).
- **Focus:** Stone border lifts to Caribbean Depth (1.5px). No background change.
- **Send button:** 36×36px icon button, attached right. Caribbean Depth color, no background at rest. Fog background on hover.
- **Multiline:** Grows with content up to 8 lines, then scrolls.

### Conversation Sidebar

- **Background:** Parchment (same as app background in light mode). No shadow against main content — separated by a 1px Stone border.
- **Width:** 260px desktop. Collapses to off-canvas on mobile.
- **Conversation item:** Full-width, 10px 12px padding, 4px radius. Title text (Inter 500, 0.875rem), timestamp label below. Hover: Fog background. Active: Caribbean Mist background, Caribbean Depth left rule — wait, **no side-stripe borders** (prohibited). Active: Caribbean Mist background + Caribbean Depth text color. No border stripe.
- **New conversation button:** Ghost button style. Full-width. Top of sidebar.

### Source Popover

Appears near a clicked citation badge, inline above or below.

- **Container:** Paper background, 1px Stone border, 12px radius. Lift shadow. Max 340px, min 240px.
- **Structure:** Document title (Title type), metadata grid (Label type, 2-col: key / value), separator, source excerpt (Body type, max 4 lines, then scroll at 9rem max-height).
- **Section label:** Charter Amber, Label type. Not a heading — a semantic marker.

### Navigation / Header

- **Style:** Parchment background. 1px Stone bottom border. 56px height.
- **Logo:** ATLAS wordmark in EB Garamond 500, ink-deep. No icon or logomark — the word is the identity.
- **Actions:** Ghost icon buttons (right side). No filled nav pills.
- **Mobile:** Hamburger icon (ghost) to toggle sidebar. No separate mobile nav bar.

## 6. Do's and Don'ts

### Do:

- **Do** use Caribbean Depth for all interactive affordances — the active state of the system speaks in one voice.
- **Do** render legal text with Inter body at 0.9375rem, 1.65 line-height, maximum 68ch. Density without cramping.
- **Do** use EB Garamond exclusively for ATLAS-brand moments: the wordmark, page-level titles, empty-state headings.
- **Do** keep all surfaces warm — Parchment, Paper, Fog — even in light/neutral contexts. Cool gray is prohibited.
- **Do** treat citation badges as first-class: ensure every badge has a popover, a hover state, and a focus state. They are the product.
- **Do** implement all three theme modes (light, dark, system) via CSS custom properties with a `.dark` class and `@media (prefers-color-scheme: dark)`.
- **Do** use `prefers-reduced-motion` to gate all animations — the globals.css already handles this; preserve it through the rebrand.
- **Do** keep the sidebar's active state visually clear through background color and text color change. Never through a left-side border stripe.

### Don't:

- **Don't** build this to look like Legis or SUIN-Juriscol — dense portal layouts with nested tables, crowded chrome, and no whitespace. ATLAS is a conversation, not a database browser.
- **Don't** build this to look like ChatGPT or Gemini — generic sans-serif everywhere, a centered logo on a white page, a thin input at the bottom. ATLAS has typographic identity and legal context baked into every element.
- **Don't** use navy + gold. It is the most legible first-order reflex for "legal tool" and the fastest way to look undifferentiated.
- **Don't** use editorial dark mode (dark background + large white serif) — it's the second-order reflex for "AI legal tool trying to look editorial." ATLAS's dark mode is deep sea, not magazine reverse.
- **Don't** use `border-left` or `border-right` greater than 1px as a colored stripe accent. Prohibited. Active states use background fills and text color change.
- **Don't** use gradient text (`background-clip: text`). Charter Amber and Caribbean Depth are single colors. They don't need gradients; they are distinctive on their own.
- **Don't** use glassmorphism. No `backdrop-filter: blur` on card-style surfaces. ATLAS surfaces are opaque.
- **Don't** add a hero metric template to /about or the empty state — big number, small label, gradient accent is a SaaS cliché.
- **Don't** use cool grays. `#64748B` (current muted) reads corporate and cool. Replace with warm equivalents (`#6b5c4e` Faded Ink family).
- **Don't** put EB Garamond on body text or UI labels. It lives at display and headline scale only; below 1.2rem it loses legibility and the distinction between the two font roles collapses.

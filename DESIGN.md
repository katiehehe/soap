---
name: Exam P Speedrun
description: A calm, academic study companion for SOA Exam P — three honest signals, never blended.
colors:
  periwinkle: "#8189d6"
  periwinkle-deep: "#6a72c4"
  sage: "#6fa892"
  honey: "#d3a95f"
  dusty-rose: "#cc8172"
  mauve: "#a888c0"
  signal-pending: "#8f897a"
  signal-progress: "#d3a95f"
  signal-mastered: "#6fa892"
  ink: "#191720"
  ink-elevated: "#221f2b"
  ink-inset: "#2a2734"
  ivory: "#ece6da"
  ivory-muted: "#a9a291"
  paper: "#f6f3ec"
  paper-ink: "#262230"
typography:
  display:
    fontFamily: "Fraunces Variable, Georgia, serif"
    fontSize: "clamp(2rem, 4.5vw, 2.9rem)"
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Fraunces Variable, Georgia, serif"
    fontSize: "1.3rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  body:
    fontFamily: "DM Sans Variable, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "DM Sans Variable, system-ui, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  sm: "8px"
  md: "12px"
  lg: "14px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.periwinkle}"
    textColor: "{colors.paper}"
    rounded: "{rounded.md}"
    padding: "0.7rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.periwinkle-deep}"
    textColor: "{colors.paper}"
  chip:
    backgroundColor: "{colors.ink-elevated}"
    textColor: "{colors.ivory}"
    rounded: "{rounded.sm}"
    padding: "0 0.95rem"
  panel:
    backgroundColor: "{colors.ink-elevated}"
    textColor: "{colors.ivory}"
    rounded: "{rounded.md}"
    padding: "1.4rem"
---

# Design System: Exam P Speedrun

## 1. Overview

**Creative North Star: "The Reading Room"**

Exam P Speedrun should feel like a quiet university reading room at night: warm lamplight
on ink-dark desks, a serif on the spine of every book, and instruments that are precise
because they are calm. It is a focused tool a candidate stares at for 150–300 hours, so
the chrome recedes and the _numbers_ lead. Personality comes through craft — a scholarly
serif, a restrained jewel-toned palette, generous whitespace — never through noise.

This system explicitly rejects the "dopamine/hyperpop" register it replaced: no neon
clashes, no gradient text, no glassmorphism, no glowing pulses, no floating emoji. It
also rejects looking like stock Anki. The honesty rule is a _visual_ commitment too:
measured numbers stay high-contrast and sober, and a withheld ("no score yet") state is
styled as honest amber, never dressed up as a win.

**Key Characteristics:**

- Dark-academia first: warm ink surface, warm-ivory text, honey/sage/periwinkle accents.
- Serif headings (Fraunces) against a clean sans (DM Sans) for body and UI.
- Restrained color: accents mark meaning and emphasis, never decoration.
- Quiet elevation: soft, diffuse shadows and thin borders; no glows or glass.
- The measured number is always the loudest calm thing on the page.

## 2. Colors

A warm, low-strain palette: deep plum-ink surfaces, warm ivory text, and five soft
jewel-toned accents used sparingly.

### Primary

- **Periwinkle** (#8189d6): the primary emphasis — brand mark, primary buttons, the map's
  centre node, active tab text, links. **Periwinkle Deep** (#6a72c4) is its hover/pressed
  and the focus ring on light surfaces.

### Secondary

- **Sage** (#6fa892): the "mastered / good" signal and a secondary accent.
- **Honey** (#d3a95f): the "in-progress" signal, the dark-mode focus ring, and warm emphasis.

### Tertiary

- **Dusty Rose** (#cc8172) and **Mauve** (#a888c0): rounding out the five-accent rotation
  for section framing (panel top-borders); never for text.

### Neutral

- **Ink** (#191720): the app surface (night mode, the default the app boots into).
- **Ink Elevated** (#221f2b): cards, panels, the top bar, raised controls.
- **Ink Inset** (#2a2734): tracks, inputs, progress rails.
- **Ivory** (#ece6da): all critical text — ~15:1 on Ink (AAA).
- **Ivory Muted** (#a9a291): secondary/supporting text.
- **Paper** (#f6f3ec) / **Paper Ink** (#262230): the matching light variant (surface / text).

### Named Rules

**The Meaning-Only Accent Rule.** Accent colours never carry body text or measured
numbers. They mark state (pending/progress/mastered), section identity, and the single
primary action — nothing decorative.

**The Fixed-Signal Rule.** Pending (warm grey), In-progress (honey), Mastered (sage) are
semantic and _fixed_. They are never rotated through the decorative accents, because they
encode a measurement.

## 3. Typography

**Display Font:** Fraunces Variable (with Georgia, serif)
**Body Font:** DM Sans Variable (with system-ui, sans-serif)

**Character:** A scholarly old-style serif for headings against a clean, humanist sans for
everything functional — the contrast axis (serif + sans) that reads "academic" without
shouting. Headings are title-case, never uppercase-black.

### Hierarchy

- **Display** (Fraunces 600, clamp(2rem, 4.5vw, 2.9rem), 1.05): page titles ("Study map",
  "Exam readiness").
- **Title** (Fraunces 600, ~1.3rem, 1.1): panel/section headings and detail titles.
- **Body** (DM Sans 400–500, ~0.95rem, 1.55): prose and explanations; cap ~68ch.
- **Label** (DM Sans 700, ~0.72rem, +0.06em, UPPERCASE): eyebrows, badges, small meta.

### Named Rules

**The Serif-Heads / Sans-Numbers Rule.** Headings are the serif; every measured value,
range, and data label is the sans, so numbers stay unambiguous and legible.

## 4. Elevation

Quiet and paper-like. Depth comes from soft, diffuse shadows plus thin hairline borders
and a subtle top-accent stripe on cards — never from glows, neon, or glass. If it looks
like it's emitting light, it's wrong.

### Shadow Vocabulary

- **sm** (`box-shadow: 0 1px 2px rgba(0,0,0,0.28)`): resting cards, chips, small controls.
- **md** (`box-shadow: 0 2px 10px rgba(0,0,0,0.32)`): panels, the map card, hover lift.
- **lg** (`box-shadow: 0 14px 40px rgba(0,0,0,0.46)`): the highest overlays only.

### Named Rules

**The No-Glow Rule.** No `box-shadow` used as a coloured glow, no `backdrop-filter` glass,
no animated gradient. Blur ≤ 10px; a colour never radiates.

## 5. Components

### Buttons

- **Shape:** rounded rectangles (12px); small controls use 8px.
- **Primary:** solid Periwinkle (#8189d6) fill, Paper/Ivory text, soft `sm` shadow,
  padding ~0.7rem 1rem.
- **Hover / Focus:** hover deepens to Periwinkle Deep (#6a72c4) with the `md` shadow; focus
  is a 2px solid ring in the theme focus colour (honey on dark, periwinkle on light) with
  a 2px offset. Never remove focus without replacement.
- **Secondary / ghost:** transparent with a thin accent border or a quiet underline; tint
  to `accent-weak` on hover. No offset "hard" shadows.

### Chips (toolbar actions)

- **Style:** Ink-Elevated background, 1px hairline border, Ivory text, sentence case, 8px
  radius, ≥40px tall.
- **State:** hover shifts border + text to Periwinkle over a faint periwinkle wash.

### Cards / Containers (panels)

- **Corner Style:** 12–14px.
- **Background:** Ink-Elevated, opaque (no glass).
- **Shadow Strategy:** `md` from Elevation.
- **Border:** 1px hairline, plus a 3px **top-accent** stripe that colour-codes the section
  (periwinkle / honey / dusty-rose / sage / mauve). Top only — never a side stripe.
- **Internal Padding:** ~1.4rem (`lg`-ish).

### Inputs / Fields

- **Style:** Ink-Inset background, 1px hairline border, 8px radius, Ivory text.
- **Focus:** 2px dashed/solid ring in the theme focus colour with offset.

### Navigation (tabs)

- Segmented pill in a muted track; the active tab is a raised Ink-Elevated pill with
  accent-coloured text and a soft `sm` shadow. Inactive tabs are Ivory-Muted, sans.

### Concept map node (signature)

- Rounded-square ("squircle", 34% radius) rendered slightly inset so it sits inside its
  layout circle and never touches its neighbour. A 2px border in the node's **semantic**
  colour (pending/progress/mastered); label is sans, centred, title-case.

## 6. Do's and Don'ts

### Do:

- **Do** keep every measured number high-contrast Ivory in the sans, always shown with its
  range and a named source.
- **Do** style the "no score yet" abstain state as honest amber (honey), clearly _not_ a win.
- **Do** use accents only for state, section identity, and the single primary action (the
  Meaning-Only Accent Rule).
- **Do** lead headings with the serif in title case; keep uppercase for small labels only.
- **Do** use thin borders (1–2px) and soft shadows (blur ≤ 10px).

### Don't:

- **Don't** dress up a guess as a measurement — no glowing/celebratory readiness score, no
  hype words behind a "no score yet" state. (Auto-fail for the project.)
- **Don't** blend the three scores into a single "% ready".
- **Don't** reintroduce the overstimulating register: no neon clashes, gradient text,
  glows, glassmorphism, or floating emoji — it's jarring over 150–300 hours of study.
- **Don't** rotate the fixed signal colours (pending/progress/mastered) through the
  decorative accents.
- **Don't** use a `border-left`/`border-right` colour stripe; card accents are top-only.
- **Don't** put accent colours on body text or numbers.
- **Don't** look like stock Anki.

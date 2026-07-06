---
name: SOAP (SOA Exam P)
description: A clean, fresh study companion for SOA Exam P, with three honest signals, never blended. The brand is the pun: SOA Exam P → SOAP.
colors:
  aqua: "#46c7d1"
  aqua-deep: "#2aa6b3"
  teal-fill: "#0c6c78"
  mint: "#58cf9f"
  lemon: "#e6c25a"
  bubblegum: "#f08ac0"
  sky: "#7fb0f0"
  signal-pending: "#8a9598"
  signal-progress: "#d3a95f"
  signal-mastered: "#5bb39a"
  water: "#0e2a30"
  water-elevated: "#143b42"
  water-inset: "#1b4a52"
  foam: "#e7f5f4"
  foam-muted: "#9db8b8"
  porcelain: "#eaf5f7"
  porcelain-ink: "#123338"
typography:
  display:
    fontFamily: "Fredoka Variable, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4.5vw, 2.9rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "0"
  title:
    fontFamily: "Fredoka Variable, system-ui, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "0"
  body:
    fontFamily: "Nunito Variable, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "Nunito Variable, system-ui, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  sm: "12px"
  md: "16px"
  lg: "22px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.teal-fill}"
    textColor: "{colors.foam}"
    rounded: "{rounded.pill}"
    padding: "0.7rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.aqua-deep}"
    textColor: "{colors.foam}"
  chip:
    backgroundColor: "{colors.porcelain}"
    textColor: "{colors.porcelain-ink}"
    rounded: "{rounded.sm}"
    padding: "0 0.95rem"
  panel:
    backgroundColor: "{colors.water-elevated}"
    textColor: "{colors.foam}"
    rounded: "{rounded.md}"
    padding: "1.4rem"
---

# Design System: SOAP (SOA Exam P)

## 1. Overview

**Creative North Star: "Squeaky clean"**

SOAP leans into its own pun: SOA Exam **P** → **SOAP**. The app should feel clean and
fresh: clear water, a faint scatter of soap suds, glossy rounded controls, and a friendly
rounded type. It is still a focused tool a candidate stares at for 150-300 hours, so the
chrome stays light and the _numbers_ lead. Personality comes through the bubbly brand and a
bright aqua palette, never through noise on the data.

The honesty rule is a _visual_ commitment: measured numbers stay high-contrast and sober in
the clean body font (never the bubbly display font), and a withheld ("no score yet") state
is styled as honest amber, never dressed up as a win. Suds, gloss, and bubbles are
decoration only: they never touch a measured number, and they honour reduced-motion.

**Key Characteristics:**

- Clean/fresh first: light "porcelain" surface (hero), deep "bath-water" teal in dark mode.
- Rounded display headings (Fredoka) against a rounded, humanist sans (Nunito) for body/UI.
- Bright aqua/teal leads; mint, sky, bubblegum, lemon round out the five-accent rotation.
- Soft, foam-like elevation and glossy soap-bar buttons; motion is quiet and state-only.
- The measured number is always the calmest, clearest thing on the page.

## 2. Colors

A clean, low-strain palette: porcelain / bath-water surfaces, deep-teal or foam text, and
five soap-bright accents used sparingly.

### Primary

- **Aqua** (#46c7d1 dark / #0f766e light): the primary emphasis, brand mark, primary
  buttons, the map's centre node, active tab text, links. **Aqua Deep** (#2aa6b3) is its
  hover/pressed; the solid CTA uses **Teal Fill** (#0c6c78) so foam text clears AA in both
  themes.

### Secondary

- **Mint** (#58cf9f / #067a5e): a secondary accent, kept distinct from the mastered signal.
- **Lemon / suds gold** (#e6c25a / #8a6d1f): warm emphasis and the in-progress signal family.

### Tertiary

- **Bubblegum** (#f08ac0) and **Sky** (#7fb0f0): rounding out the five-accent rotation for
  section framing (panel top-borders); never for text.

### Neutral

- **Water** (#0e2a30): the app surface in dark mode.
- **Water Elevated** (#143b42): cards, panels, the top bar, raised controls (dark).
- **Water Inset** (#1b4a52): tracks, inputs, progress rails (dark).
- **Foam** (#e7f5f4): critical text on water (AAA).
- **Foam Muted** (#9db8b8): secondary/supporting text (dark).
- **Porcelain** (#eaf5f7) / **Porcelain Ink** (#123338): the light hero variant (surface / text).

### Named Rules

**The Meaning-Only Accent Rule.** Accent colours never carry body text or measured
numbers. They mark state (pending/progress/mastered), section identity, and the single
primary action, nothing decorative.

**The Fixed-Signal Rule.** Pending (cool grey), In-progress (suds gold), Mastered (fresh
mint) are semantic and _fixed_. They are never rotated through the decorative accents,
because they encode a measurement.

## 3. Typography

**Display Font:** Fredoka Variable (with system-ui, sans-serif)
**Body Font:** Nunito Variable (with system-ui, sans-serif)

**Character:** A rounded, friendly display face for headings and the SOAP wordmark against a
rounded humanist sans for everything functional, playful but highly legible. Headings are
title-case, never uppercase-black.

### Hierarchy

- **Display** (Fredoka 700, clamp(2rem, 4.5vw, 2.9rem), 1.05): page titles ("Study map",
  "Exam readiness") and the SOAP wordmark.
- **Title** (Fredoka 600, ~1.3rem, 1.1): panel/section headings and detail titles.
- **Body** (Nunito 400-700, ~0.95rem, 1.55): prose and explanations; cap ~68ch.
- **Label** (Nunito 700, ~0.72rem, +0.06em, UPPERCASE): eyebrows, badges, small meta.

### Named Rules

**The Round-Heads / Clean-Numbers Rule.** Headings are the rounded display font; every
measured value, range, and data label is the clean body font with tabular figures, so
numbers stay unambiguous and legible, never the bubbly display font.

## 4. Elevation

Quiet and foam-like. Depth comes from soft, diffuse teal-tinted shadows plus thin hairline
borders and a subtle top-accent stripe on cards. Primary buttons add a soap-bar gloss (a
soft white top highlight), but nothing radiates light like neon or glass.

### Shadow Vocabulary

- **sm** (`box-shadow: 0 1px 3px rgba(6,40,45,0.22)`): resting cards, chips, small controls.
- **md** (`box-shadow: 0 6px 18px rgba(6,40,45,0.24)`): panels, the map card, hover lift.
- **lg** (`box-shadow: 0 18px 46px rgba(6,40,45,0.38)`): the highest overlays only.

### Named Rules

**The No-Glow Rule.** No `box-shadow` used as a coloured glow, no `backdrop-filter` glass.
The soap-bar gloss is a soft white top highlight, not a radiating colour.

## 5. Components

### Buttons

- **Shape:** rounded pills; small controls use a 12px radius.
- **Primary:** solid Teal Fill (#0c6c78) with a soap-bar gloss overlay, Foam text, soft
  `sm` shadow + a subtle inset top highlight, padding ~0.7rem 1rem.
- **Hover / Focus:** hover deepens to Aqua Deep (#2aa6b3) with the `md` shadow; focus is a
  2px solid ring in the theme focus colour (aqua on dark, teal on light) with a 2px offset.
  Never remove focus without replacement.
- **Secondary / ghost:** transparent with a thin accent border or a quiet underline; tint
  to `accent-weak` on hover. No offset "hard" shadows.

### Chips (toolbar actions)

- **Style:** elevated (clean-tile) background, 1px hairline border, ink/foam text, sentence
  case, 12px radius, ≥40px tall.
- **State:** hover shifts border + text to Aqua over a faint aqua wash.

### Cards / Containers (panels)

- **Corner Style:** 16-22px (bubbly).
- **Background:** elevated surface, opaque (no glass).
- **Shadow Strategy:** `md` from Elevation.
- **Border:** 1px hairline, plus a 3px **top-accent** stripe that colour-codes the section
  (aqua / mint / lemon / bubblegum / sky). Top only, never a side stripe.
- **Internal Padding:** ~1.4rem (`lg`-ish).

### Inputs / Fields

- **Style:** inset background, 1px hairline border, 12px radius, ink/foam text.
- **Focus:** 2px dashed/solid ring in the theme focus colour with offset.

### Navigation (tabs)

- The active tab is an accent-tinted pill (soft aqua fill + faint ring) with accent-coloured
  text; inactive tabs are muted. Labels are the body sans.

### Concept map node (signature)

- Rounded-square ("squircle", 34% radius) rendered slightly inset so it sits inside its
  layout circle and never touches its neighbour, with a soft top-left **bubble sheen**. A
  2px border in the node's **semantic** colour (pending/progress/mastered); label is the
  display font, centred, title-case.

## 6. Do's and Don'ts

### Do:

- **Do** keep every measured number high-contrast in the clean body font (tabular figures),
  always shown with its range and a named source, never the bubbly display font.
- **Do** style the "no score yet" abstain state as honest amber, clearly _not_ a win.
- **Do** use accents only for state, section identity, and the single primary action (the
  Meaning-Only Accent Rule).
- **Do** lead headings with the serif in title case; keep uppercase for small labels only.
- **Do** use thin borders (1-2px) and soft shadows (blur ≤ 10px).

### Don't:

- **Don't** dress up a guess as a measurement: no glowing/celebratory readiness score, no
  hype words behind a "no score yet" state. (Auto-fail for the project.)
- **Don't** blend the three scores into a single "% ready".
- **Don't** let the playful chrome touch the data: bubbles, suds, and gloss stay off every
  measured number, and all bubble motion honours reduced-motion.
- **Don't** rotate the fixed signal colours (pending/progress/mastered) through the
  decorative accents.
- **Don't** use a `border-left`/`border-right` colour stripe; card accents are top-only.
- **Don't** put accent colours on body text or numbers.
- **Don't** look like stock Anki.

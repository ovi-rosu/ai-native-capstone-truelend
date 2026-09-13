# Aesthetic direction — TrueLend

One visual contract for every mockup and for the production screens that follow.
Committed here so seven mockups read as one product rather than seven Tailwind
defaults.

## Direction

**Institutional ledger, editorially typeset.** A lending back office that looks
like a printed rate sheet: warm paper ground, ink-dark structure, hairline rules
instead of drop shadows, dense tabular data treated as the hero. Numbers are the
content, so numbers get the typographic care — tabular figures, right-aligned
money columns, generous row height. No glassmorphism, no gradient hero, no
rounded-2xl card soup.

## Typography

- Display / headings: **Fraunces** (variable serif, high optical size) —
  `https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&display=swap`
- Body / UI: **Public Sans** — `family=Public+Sans:wght@400;500;600;700`
- Numerals: **IBM Plex Mono** for every monetary and date column
  (`family=IBM+Plex+Mono:wght@400;500;600`), always with `font-variant-numeric: tabular-nums`.
- Never Inter, Roboto, Arial or a system default.

## Palette (placeholder, brand-swappable)

| Token | Hex | Use |
|---|---|---|
| `ink` | `#14231D` | Text, rules, table headers |
| `ink-muted` | `#4E6158` | Secondary text, labels |
| `paper` | `#F7F4EC` | Page ground |
| `paper-raised` | `#FFFDF7` | Table and panel surfaces |
| `brass` | `#9A6B1F` | Primary action, active nav, focus ring |
| `signal-red` | `#8E241C` | AUTO_REJECT, NPA, destructive |
| `signal-amber` | `#8A5B12` | MANUAL_REVIEW, DPD-30 / DPD-60 |
| `signal-green` | `#1D5C41` | AUTO_APPROVE, VERIFIED, CURRENT |
| `rule` | `#D8D0BE` | 1px hairlines, table dividers |

Every pairing above clears WCAG AA on `paper` (4.5:1 for body, 3:1 for large).
Status is never colour alone — each badge carries its literal label text.

## Spatial language

- 8px baseline grid; page max-width 1180px; single left rail 220px on desktop.
- Hairline borders (`1px solid rule`), square corners except a 2px radius on
  inputs and buttons. No shadows above `0 1px 0 rule`.
- Tables: header in small-caps Public Sans 600 with letter-spacing, 44px rows,
  money right-aligned in IBM Plex Mono, zebra off, hairline between rows.
- Focus: 2px `brass` outline with 2px offset, always visible, never removed.

## Data rules

- Money renders exactly as the API sends it — a quoted 2dp string — with a
  thousands separator added for display only. Mockups must never show a
  float-looking value such as `450000.0` or `450000`.
- Every displayed field must exist in `specs/design/api-contracts.md`. Use the
  schema field name in `data-*` attributes and JavaScript state; the human label
  can differ.
- Realistic Indian-market data: Priya Raghavan, Arjun Menon, Kavya Iyer;
  amounts in the 80,000 to 24,00,000 range; dates in 2026.
- Delinquency buckets display as `CURRENT`, `DPD-30`, `DPD-60`, `DPD-90`, `NPA`.
- Decision outcomes display as `AUTO_APPROVE`, `AUTO_REJECT`, `MANUAL_REVIEW`.

## Technical contract for every mockup

Self-contained single HTML file: React 18 UMD + Babel standalone + Tailwind CDN
from versioned unpkg/cdn URLs, Google Fonts link, Tailwind config extended with
the tokens above, hardcoded data matching the API shapes, no network calls, no
`localhost`. Semantic landmarks (`nav`, `main`, `table`, `form`), labelled
controls, one working primary interaction per screen, readable at 375px and
1280px.

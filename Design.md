# Design.md

UI/design rules for agents working on the Azure RAG Console (`ui/`).

Read this before any styling, layout, or frontend visual change.

## Product look

This is an **Azure admin console**, not a marketing site and not a generic AI chat skin.

- Light mode only unless the user explicitly asks for dark mode.
- Visual language: Azure blue accent, light gray canvas, white surfaces, compact chrome.
- Prefer calm utility UI over decorative gradients, glow, purple themes, or heavy card stacks.
- Brand signal is the blue bot mark + “Azure RAG Console” title in the header.

## Stack rules

| Do | Don't |
|---|---|
| Style with [`ui/src/app/globals.css`](ui/src/app/globals.css) tokens and classes | Add Tailwind/shadcn/MUI unless the user asks |
| Reuse existing chrome components (`console-header`, status chips, corpus buttons) | Duplicate header/status markup across pages |
| Bridge CopilotKit via CSS variables on `.chat-workspace [data-copilotkit]` | Fork CopilotKit internals or rebuild chat from scratch |
| Keep diffs small and CSS-first for visual polish | Introduce a second design system |

Fonts: Geist + Geist Mono via `next/font` in [`ui/src/app/layout.tsx`](ui/src/app/layout.tsx).

## Design tokens

Canonical tokens live on `:root` in `globals.css`. Prefer tokens over hardcoded colors.

| Token | Role |
|---|---|
| `--ink` | Primary text |
| `--muted` / `--muted-ink` | Secondary text (readable gray) |
| `--line` | Borders / dividers |
| `--surface` | White panels |
| `--canvas` | Page background |
| `--azure` | Primary accent / actions |
| `--green` / `--danger` / `--warning` | Status semantics |
| `--accent-soft` / `--accent-ink` | Soft blue fills and accent text |
| `--radius-sm/md/lg` | Corner radius scale |
| `--shadow-card` / `--shadow-soft` | Elevation |
| `--focus-ring` | Focus outlines |

### Critical: CopilotKit token collision

Inside `.chat-workspace [data-copilotkit]`, CopilotKit remaps `--muted` to a **background** color.

- Never use `var(--muted)` for text that renders inside CopilotKit (citations, source rows, custom chat chrome).
- Use `--muted-ink`, `--ink`, or `--accent-ink` for text contrast.
- When bridging CopilotKit theme vars, set `--muted-foreground` for disclaimer/secondary text; keep `--muted` as the CopilotKit surface token.

## Layout structure

```
console-shell
├── console-header          (shared: brand + nav)
└── console-main
    ├── status-strip        (chat page only, via StatusGate)
    └── chat-workspace      (chat card or corpus card)
```

Rules:
- Use [`ui/src/app/console-header.tsx`](ui/src/app/console-header.tsx) for both `/` and `/corpus`.
- Chat content lives inside `.chat-workspace`; corpus reuses the same workspace framing with `.corpus-workspace`.
- Avoid nested “card inside card” heaviness: keep outer workspace shadow soft.

## Component conventions

### Navigation

- Interactive nav (`Corpus`, `Back to chat`) must look like **buttons**: border, surface fill, readable ink, hover state.
- Do not leave bare underlined browser-default links in the header.
- Use `aria-current="page"` for the active route; active style is soft Azure fill, not default link blue.

### Status strip

- Use chip groups (connection/health left, metrics right).
- Status must not rely on color alone: keep label text (`Connected`, `Degraded`, `Unavailable`).
- On mobile, keep Search/OpenAI chips; truncate long metrics instead of hiding all status.

### Buttons

- Primary action: Azure fill (`corpus-btn-primary` / equivalent).
- Secondary: outlined surface button.
- Destructive: red text/border (`corpus-delete`), soft red hover.
- Disabled: reduced opacity + `not-allowed` cursor.

### Citations / sources

- Source rows must remain high-contrast and scannable.
- Prefer document name + short chunk preview so duplicate filenames are distinguishable.
- Keep citation markers clickable and focus-visible.
- Minimize `!important`; if needed, scope it under `.chat-workspace`.

### Corpus table

- Keep table inside `.corpus-table-wrap` with horizontal scroll on narrow screens.
- File names may wrap on mobile; sizes use mono.
- Empty/loading states use dashed placeholder panels, not blank white space.

## CopilotKit theming

Theme CopilotKit by overriding CSS variables under `.chat-workspace [data-copilotkit]`:

- Map `--primary` to `--azure`.
- Map fonts to Geist.
- Keep welcome suggestion pills compact: allow wrap, cap width, center the suggestion container.
- Target stable selectors when possible (`[data-testid="copilot-suggestions"]`, `[data-testid="copilot-suggestion"]`).
- Do not fight CopilotKit with broad `!important` overrides unless a specific conflict is proven.

## Responsive rules

Breakpoint: `720px`.

- Mobile chat workspace goes full-bleed (no outer card border/shadow).
- Header service labels may collapse to icons; keep Corpus / Back actions available.
- Never clip welcome suggestions or corpus content with `overflow: hidden` on the workspace card. Prefer `overflow-x: hidden` + `overflow-y: auto`.
- Corpus card must stay full-width and centered on mobile (`min-width: 0`, no off-screen offset).

## Accessibility

- Preserve visible `:focus-visible` rings on links, buttons, summaries.
- Status and indexer badges need text labels, not only colored dots.
- Disclaimer and secondary text must meet readable contrast against white surfaces.
- Prefer semantic controls (`button`, `Link`, `summary`) over clickable `div`s.

## Change workflow for UI tasks

1. Inspect current tokens/classes in `globals.css` before inventing new ones.
2. Prefer extending existing classes over new one-off styles.
3. After visual changes, verify:
   - `/` welcome screen (suggestion size/alignment)
   - `/` answered chat (citations contrast)
   - `/corpus` table + actions
   - Mobile width (~390px) for overflow/clipping
4. Run `cd ui && npm test && npm run lint`.
5. If README screenshots no longer match, note that `scripts/capture_readme_demo.mjs` can refresh them (do not regenerate unless asked).

## Explicit non-goals (unless requested)

- Dark mode / theme toggle
- Tailwind or component-library migration
- Custom chat UI replacing CopilotKit
- Styled modal replacing `window.confirm` for deletes
- Marketing/landing-page visual treatments

## Quick regression checklist

- [ ] Citation source text is readable (not washed out)
- [ ] Corpus nav looks like a button
- [ ] Suggestion chips are compact and not clipped on mobile
- [ ] Status chips remain understandable without color alone
- [ ] No new hardcoded colors that bypass tokens
- [ ] No second styling system introduced

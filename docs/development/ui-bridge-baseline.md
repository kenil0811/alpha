# UI foundation: Bridge baseline (Phase 1)

What landed, for the four parallel agents building on it.

## Tokens
`apps/desktop/src/styles/tokens.css` is the single source: Bridge's light/dark palette as
`--bridge-*` vars, type scale (`--text-*`), spacing (`--space-*`), radii, shadows. `app.css` maps
the app's existing semantic names (`--bg`, `--surface`, `--text`, `--primary`, `--good`, `--bad`,
`--warn`, …) onto the `--bridge-*` values, so every existing component kept working unchanged.
Base font is 17px (`html { font-size: 17px }`); h1 is serif 34px/400, h2 26px/600, h3 19px/500, h4
17px/500 navy-mid; minimum text size anywhere is 12px. Fonts: `@fontsource-variable/geist` and
`@fontsource-variable/source-serif-4`, imported at the top of `app.css` (bundled, works offline,
satisfies the existing Tauri CSP without an external font host).

**Rule: only this foundation edits `tokens.css`/`app.css`. Each feature area owns its own `.css`
file** (see `apps/desktop/src/ui/*.css` for the pattern — one file per component, imported by the
component itself).

## Theme
Default is light (`apps/desktop/src/shell/theme.tsx`, `useTheme`). Match Mac / Light / Dark stays
in Settings → Appearance (`shell/Info.tsx`). The compact toggle was removed from the rail.

## Primitives — `apps/desktop/src/ui/`
Import from `./ui` (barrel at `ui/index.ts`).

- `Button({ variant: "default"|"destructive"|"outline"|"secondary"|"ghost"|"link", size: "sm"|"default"|"lg"|"icon", ...ButtonHTMLAttributes })`
- `IconButton({ "aria-label": required, size: "sm"|"default", ...ButtonHTMLAttributes })`
- `Badge({ variant: "success"|"warning"|"danger"|"neutral"|"info"|"default" })`
- `Input`, `Textarea` — thin styled wrappers over the native elements, forwardRef.
- `Tooltip({ content, side? })` + `TooltipProvider` (wrap once near the app root; already done in `App.tsx`) — Radix.
- `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent({ align })`, `DropdownMenuItem`,
  `DropdownMenuCheckboxItem`, `DropdownMenuLabel`, `DropdownMenuSeparator` — Radix.
- `Popover`, `PopoverTrigger`, `PopoverContent({ align })` — Radix.
- `Select`, `SelectTrigger`, `SelectContent`, `SelectItem({ value })` — Radix.
- `Dialog`, `DialogTrigger`, `DialogContent({ title, description? })`, `DialogClose` — Radix.
- `StandardDropdown({ options: {value,label}[], value, onChange, onAdd?, addLabel?, addDisabledReason? })`
  — ports Bridge's behavior: search past 6 options, pinned "+ Add…" row, disable-with-reason. Has
  its own test (`ui/StandardDropdown.test.tsx`).

Radix's Popover/Select/Tooltip need `ResizeObserver`; jsdom doesn't have one, so
`src/test/setup.ts` now stubs a no-op — any new test that renders these primitives gets it for
free.

**Not landed:** Tabs and Toast primitives. No caller needs them yet — the module page's own
tab/toggle UI (`.subtabs`/`.toggle` in `app.css`) already works and nothing calls a toast. Add
them when a real caller needs them rather than speculatively.

## Icons
All emoji/unicode glyphs in the shell chrome are replaced with `lucide-react`: rail nav (Home,
Activity, Connections, Settings, +New, collapse toggle), module icons (keyword-matched to
Utensils/Dumbbell/Briefcase/BookOpen/CreditCard/ListChecks, else `Boxes`), and the small icon
glyphs in the assistant panel, voice mic button, module page gear row, data table row-delete, and
search/filter bar (`modules/blocks.tsx`, `modules/DataSection.tsx`, `modules/ModulePage.tsx`,
`assistant/AssistantPanel.tsx`, `shell/voice.tsx`). A declared screen's `screen.icon` string
resolves through lucide's icon map (`modules/ModulePage.tsx`, `resolveIcon`) and falls back to
`Boxes` for anything that isn't a real lucide name.

## Runtime status
The rail no longer shows a status text row. The Alpha mark carries a small dot
(`.brand__mark--connected/--unavailable`) plus a `Tooltip` and an `role="status"` + `sr-only` text
node, so it's still screen-reader/test-visible without taking rail space.

## Routes, panels (drag-resize), rail reordering/hide menu — NOT LANDED
Given the size of the remaining asks (react-router migration off the in-memory `Surface` state,
Bridge's full `PanelControl` with drag-resize/extended mode/stepped-Escape, native drag-to-reorder
modules, and the per-row Hide/Rename context menu), none of these landed in this pass — the
existing `Surface`-state navigation, the rail's collapsed/expanded toggle, and the plain module
list all still work exactly as before, just re-skinned. Recommend a dedicated follow-up task per
item; the tokens/primitives here don't block starting any of them (`Button`/`IconButton`/
`DropdownMenu`/`Tooltip` are what a panel/rail-menu rebuild would reach for first).

## Deps added
`lucide-react`, `@radix-ui/react-{dialog,dropdown-menu,popover,select,tooltip}`,
`react-router` (installed, not yet wired — see above), `@fontsource-variable/geist`,
`@fontsource-variable/source-serif-4`.

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

## Panel control — `ui/panel.tsx`
Ports Bridge's `PanelControl` (`platform/apps/web/src/app/components/shared/PanelControl.tsx`) as
plain CSS/React (no Tailwind here) instead of a rendered wrapper component, so the rail and the
assistant each own their own markup and just consume the hook:

- `usePanelControl({ defaultWidth, minWidth, maxWidth, storageKeyWidth, storageKeyCollapsed, snap?,
  snapMidpoint?, migrateWidthKeys?, migrateCollapsedKeys?, initialCollapsed? })` → `{ collapsed,
  mode: "collapsed"|"expanded"|"extended", width, displayWidth (live value during a drag),
  isDragging, setCollapsed, toggleCollapsed, resizeBy(delta), startDrag(mouseEvent),
  handleEscape() ⇒ boolean }`. `snap: true` (the rail) snaps to collapsed/expanded on drag
  release at `snapMidpoint`; omitted (the assistant) resizes continuously.
- `handleEscape()` steps extended → expanded → collapsed, one level per call, and returns whether
  it did anything — callers gate it on focus-within/no-open-overlay themselves (see `App.tsx`'s
  single document `keydown` listener, which checks `railRef`/`assistRef.contains(activeElement)`
  and bails if a `[role=dialog|menu|listbox]` is open).
- `CollapseToggleButton({ side, collapsed, onClick, controls, className? })` — PanelLeftClose/
  PanelRightClose when expanded, ChevronsRight/ChevronsLeft when collapsed; sets
  `aria-expanded`/`aria-controls`.
- `ResizeHandle({ side, onMouseDown, onStep, label, value, min, max, isDragging })` —
  `role="separator"`, `tabIndex=0`, ArrowLeft/Right step ±16px via `onStep`, hairline + grip hidden
  until hover/focus/drag (`panel.css`).
- `CollapsedStrip` — a plain button wrapper for a collapsed panel's icon strip.

Persisted keys: `alpha.rail.width` / `alpha.rail.collapsed` (rail, snap, 76/220/360),
`alpha.assistant.width` / `alpha.assistant.collapsed` (assistant, continuous, 48-collapsed-strip/
286/520). The old `alpha.assistant.open` per-surface (home vs. module) open/closed map is kept as
a *separate* concern in `App.tsx` (`openByKind`) — that's "is the assistant visible on this kind of
surface", independent of the panel's own collapsed width state; a person can collapse the
assistant to its 48px strip without losing the per-surface open/closed memory.

Test: `ui/panel.test.tsx` covers width clamping, extended mode, the three-step Escape sequence,
persistence across remount, and legacy-key migration — via `renderHook`, no DOM.

## Routing — HashRouter
`App.tsx` wraps the shell in `<HashRouter>` and derives `Surface` from `useLocation().pathname`
with a small regex parser (`surfaceFromPath`/`sectionFromPath`) rather than a `<Routes>` tree —
every destination already went through one switch statement, so a routes tree would just duplicate
it. Paths: `/` home, `/activity`, `/connections`, `/settings`, `/m/:moduleId`,
`/m/:moduleId/:section` (section is `app|data|activity|settings`, passed to `ModulePage` as a new
optional `section`/`onSectionChange` prop pair — omit both and `ModulePage` manages the section
itself, unchanged, for any caller that doesn't route). `setSurface` now calls `navigate(...)`;
back/forward work because the browser owns the history. On first mount at `/`, `App.tsx` replays
`alpha.surface` from localStorage once (`restoredOnce` ref) so a restart reopens the same page —
after that the URL is the only source of truth. Rail items are still plain `<button>`s (not
`<Link>`) that call the passed-in `onGo`/`navigate`, to keep them `role="button"` (existing tests
assert `getByRole("button", { name: "Settings" })`, etc.) while still being real URL navigation.
Tests: jsdom's `window.location.hash` persists across tests in the same file (unlike component
state), so `test/setup.ts` resets it to `""` in `afterEach`.

## Rail — reorder, hide/show
`shell/Rail.tsx` now takes a `panel: PanelControl` prop (from `usePanelControl`, owned by
`App.tsx`) instead of `collapsed`/`onToggleCollapsed`. Each module row is a `.navrow` with the nav
button plus a `DropdownMenu` (Open / Hide from sidebar) behind a hover-revealed `⋮`; hidden ids
persist to `alpha.rail.hiddenModules`, and a "N hidden · Show all" row appears at the bottom of the
list when any are hidden. Native HTML5 drag-and-drop (`draggable`, `onDragStart`/`onDragOver`/
`onDrop`) reorders rows; order persists to `alpha.rail.moduleOrder` (unknown/new modules sort after
known ones by server order). Rename/Delete were checked against `core/client.ts` — no call exists
for either, so both were left out per the brief.

## Tabs, Toast — `ui/Tabs.tsx`, `ui/toast.tsx`
- `Tabs({ items: {value,label}[], value, onChange, "aria-label" })` — `role="tablist"`/`"tab"`,
  `aria-selected`, roving `tabIndex`, Arrow/Home/End. Plain CSS, no Radix — the module page's
  existing `.subtabs` still uses its own toggle and was left alone (not a trivial swap: it also
  carries a badge count).
- `ToastProvider` (wired once in `App.tsx`, wrapping `HashRouter`) + `useToast() → { show(message,
  action?) }`. One `role="status" aria-live="polite"` region, auto-dismiss 5s, optional action
  button. The region only renders while a toast is queued, so it never collides with the rail's own
  `role="status"` runtime dot in an accessibility-tree query.

## PageHeader — `ui/PageHeader.tsx`
`PageHeader({ title, right?, center? })`, a 56px `border-bottom` row matching the rail's `.brand`
and the assistant's `.assist__head`, both now also 56px. Added as a primitive for the next agent to
adopt per-page; existing page headings (Home/Activity/Connections/Settings h2s) were **not**
retrofitted to it in this pass — flag as a follow-up if pixel alignment across every page header
matters before ship.

## Layout — flex shell, panels, mobile
`.app` is a flex row, `100dvh`: `.rail` (flex: none, width driven by `panel.displayWidth` inline
style) | `.main` (flex: 1, min-width: 0, overflow: auto) | `.assist` (flex: none, same pattern).
Nothing overlays `.main` at ≥1024px. `--shadow-shell-right`/`--shadow-shell-left` give each panel a
seam shadow. Rail collapsed = 76px icon+12px-label-stacked rows (not icon-only); assistant
collapsed = 48px strip (`.assist--collapsed`) showing a `MessageCircle` icon button that expands it
— the floating bottom-right "Assistant" FAB is gone.

Below 640px (`isNarrow` in `App.tsx`, tracked via a `resize` listener): the rail and its resize
handle are hidden by CSS, a `.tabbar` (56px: Home, Modules, Assistant, Settings) replaces them, and
`Modules` opens a `.drawer-sheet` (rail rendered inside a `min(86vw,320px)` left sheet) while the
assistant becomes a `.assist--overlay` covering the full viewport. This mobile pass is intentionally
lighter than desktop — no drag-resize, no reorder/hide menu inside the drawer's rail instance (it's
the same `Rail` component, so those still technically work, just untested at this width) — flag for
a dedicated mobile-pass task if that matters before ship.

From 640px to 1023px (`compact` in `App.tsx`) the rail is drawn collapsed and Chief of Staff
opens over the page (the `@media (max-width: 1023px)` rule in `assistant.css`), so the page keeps
its room down to the window's 768px minimum. Both are view-only overrides: the saved widths and
collapse choices come back once the window is wide again.

## Fit and overflow (strong rule)

Nothing spills out of its box at any window size from the 768x560 minimum up.

- Text fits its place: shorten the copy first; a one-line ellipsis (with the full text in
  `title=`) only where the text is the person's own (a project name, a session title).
- Shrink order: a search bar or an empty field gives up width first (down to a usable
  minimum, ~64-96px) before labels or filled values truncate.
- Placeholders fit their field. Write them short enough not to clip at the narrowest width.
- Rows wrap rather than squeeze: `.item__body` keeps 180px before its controls wrap below it.
- Check before shipping a layout change: run `apps/desktop/tools/layout-check.js` in the dev
  tools console at 768x560, 1100x760 and 1440x900 on every page; it must return `[]`.

## Model providers

- Each way of reaching a model is its own row in Settings -> Models: Claude (browser sign-in
  through the `claude` CLI) and Claude API (an Anthropic key) are separate rows, never one row
  with a mode switch.
- The star on a row is the only place the default provider is chosen; one row is always starred.
- Not connected means the next step happens by itself: the "not connected" card on the newest
  turn opens the provider's browser sign-in straight away and resends the message once it lands.

- Rows sort by status: errors first, then connected, then not connected.
- Codex is installed for the person, never through a terminal: "Install Codex" links the copy
  the ChatGPT app ships (or installs it with npm in the background), then "Connect".
- The composer never shows the chosen model; it lives in + -> Advanced.

## Vocabulary (strong rule)

- A module is a **project** in everything a person reads; one filed inside a project folder is
  a **sub project**. Code identifiers, routes, the `.alphamodule` format and SDK names keep
  "module".
- New project opens one picker: search, Import a project… first, Blank project, then Commons
  (from `GET /api/commons`; the section shows nothing at all while it's empty).

## UI copy and density (strong rule)

The audience is executives: to the point, minimal distraction.

- Titles/labels are short and specific. No descriptive sentence under a title or inside a card
  (kill `item__sub`/`faint`/`modhead__desc`-style paragraph descriptors) — the explanation goes in
  an `InfoTip` (`ui/InfoTip.tsx`, hover/focus tooltip) next to the title, or a native `title=`
  attribute, never as visible body text.
- Empty states are one short line.
- Inputs are sized to their content, not full width. A key/id/model-name field is a compact
  single-line input, roughly 240–320px, not a stretched full-row field. Only genuinely long
  content (notes, prompts, free text) gets a wide or multi-line field.
- Minimal, elegant, professional by default. Depart from it only when explicitly asked.
- Never drop information needed to act — errors, warnings, destructive confirmations stay
  visible, just kept to one line.

## Deps added
`lucide-react`, `@radix-ui/react-{dialog,dropdown-menu,popover,select,tooltip}`, `react-router`
(now wired — `HashRouter`), `@fontsource-variable/geist`, `@fontsource-variable/source-serif-4`.
No new dependency for Tabs/panel-resize/drag-reorder — all native DOM APIs (HTML5 drag-and-drop,
`mousemove`/`mouseup` listeners, `role="separator"` keyboard handling).

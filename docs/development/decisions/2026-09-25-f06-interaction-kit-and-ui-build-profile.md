# Decision: F06 interaction kit, UI build profile and generated-UI constraints

Date: 2026-09-25. Recorded by the coding agent (self-review). No bundle document is modified.

## 1. Plain React + CSS tokens; Radix, Tailwind and TanStack are not used yet

The prototype scope says to use Radix, Tailwind and TanStack "selectively". None is needed for the
F06 components:

- **Radix Dialog** (the drawer) relies on react-remove-scroll, which injects `<style>` elements at
  runtime. Generated UI runs under a hash-pinned `style-src`, so those styles are blocked. The kit
  uses the native modal `<dialog>` instead, which provides an inert background, Escape to close
  and focus containment, and supports returning focus.
- **Tailwind** would add a CSS build step and a utility vocabulary to the UI profile. Kit classes
  plus CSS custom properties give generated UI the same tokens with a fixed, auditable stylesheet.
- **TanStack Table**: filtering, sorting and paging happen in Core through declared views, so the
  table holds one page and needs no client table engine.

Any of these can be added later through the UI profile when a component needs it. The addition
must be qualified against the generated-UI CSP.

## 2. Generated UI never relies on native form submission

App UI frames are sandboxed without `allow-forms`, as the App UI Bridge contract requires. The
HTML form submission algorithm then returns before a `submit` event is fired, so a plain
`<form onSubmit>` never saves. The rendered check found this. The kit's `Form` performs
submission itself on Enter in single-line fields and on kit submit buttons. `QuickEntry` and all
compositions use it, and a test blocks submit events to reproduce the sandbox. `REFERENCE.md`
tells the builder to use `Form`, never `<form>`.

## 3. Read views are declared in `app.yaml` and enforced by Core

`ui.views` fixes each view's collection, base filter, projection, filterable and sortable fields
and page limit, or its grouping and metrics for aggregates. `ui.actions` lists the UI-callable
actions, which must be `invocable_from: ui`. The shell derives the bridge grant from this
declaration. Core enforces each view on `POST /api/apps/{id}/views/{view}/query`, then applies the
normal typed query compiler and platform limits. The frame's own claims widen nothing.

## 4. One managed UI build profile; the platform owns the build configuration

`tools/build_ui_profile.py` builds and packs `@alpha/ui-bridge` and `@alpha/ui-kit` as JavaScript
tarballs, which are byte-reproducible. It installs them offline with React, Vite and the React
plugin at exact versions into a sealed `uiprof-<id>`. Files are copied, not hard-linked, lifecycle
scripts are disabled, and the lock is checked with `--frozen-lockfile`. The profile records the
whole installed closure (22 packages) and is verified by Core like the Python profile.
`tools/ui_build/build_app_ui.mjs` compiles an App's `ui/` source against that profile using a
platform-owned Vite configuration. Only `.ts`, `.tsx`, `.css` and `.json` sources are accepted;
there is no App package.json, plugin or config. It emits one static HTML document with a
hash-pinned CSP and a `build.json` naming the exact profile and packages. The build fails on any
module resolved outside the App source and the profile, or on any remote import.

## 5. Where the compositions render during development

In the native window, App UI will be served from sealed Versions through `alpha-ui://` (F08). A
`srcdoc` frame in the shell inherits the shell's CSP, and the Claude browser pane refuses requests
made by sandboxed frames (`ERR_BLOCKED_BY_CLIENT`). The F06 compositions are therefore exercised
on a development-only page, `apps/desktop/kit-fixture.html`. It is not in the shell or the
packaged app. It uses the shell's own Core client and bridge host code against a development Core
with the neutral entries fixture installed. The shell's CSP is unchanged.

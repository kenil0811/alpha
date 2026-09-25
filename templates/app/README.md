# App template

The starting shape of a generated App. The builder copies this directory into its workspace and
fills it in; it is a bootstrap and composition example, not a copy of any shared package.

- `app.yaml.template`: the source contract (Current Release Specification §3). `{{...}}` markers
  are filled by the platform: the exact runtime profile ID, the App id and name.
- `src/app_code/handlers.py`: action handlers. Import only `alpha_sdk` and the standard library;
  `ctx.records`, `ctx.artifacts` and `ctx.models` are the only ways to reach data.
- `ui/src/main.tsx`: optional custom UI. Import only `react`, `react-dom` and `@alpha/ui-kit`
  (plus the App's own files). It reads through the views declared under `ui.views` and changes
  data only through the actions listed under `ui.actions`. It is compiled by the platform against
  the pinned UI build profile; there is no per-App package.json, bundler config or server.

See `@alpha/ui-kit/REFERENCE.md` (shipped inside the UI profile) for components and patterns.

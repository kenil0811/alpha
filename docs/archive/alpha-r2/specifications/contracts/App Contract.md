# App contract

Baseline R2 · contract 0.2. Current Release Specification sections 2–5 own normative fields.

An App is user-created reusable work, with stable identity, generated behavior, optional collections/UI and optional triggers. It can produce an external update or artifact without custom UI. The platform must not require a table/dashboard or constrain Apps to example domains.

The source contract declares intent and code bindings. Core validates and seals it into a Version, then resolves current resources/config/grants into a Release. Source metadata cannot grant authority or embed account secrets. Actions are the shared callable surface for assistant, UI and scheduling. Real handler imports/signatures/execution are verified in a disposable worker.

Mutable records, configuration history, connections and run evidence live outside source/version directories. Tasks use their own owner identity and do not need an App to access shared capabilities. Contract/schema implementation starts incrementally in F02/F05/F07.

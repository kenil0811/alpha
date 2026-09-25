// Template UI: a quick entry and the recent list. Replace with the App's real interaction.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import { AlphaApp, Page, QuickEntry, RecordTable, Section, formatDay, useAction, useView, type RecordRow } from "@alpha/ui-kit";

type Item = { title: string; noted_on: string };

function App() {
  const add = useAction("add_item");
  const recent = useView<Item>("items.recent", { limit: 20 });
  return (
    <Page title="Items" description="Add an item and see the most recent ones.">
      <Section title="Add">
        <QuickEntry
          label="New item"
          parse={(text) => (text.trim() ? { status: "ok", value: text.trim(), summary: text.trim() } : { status: "empty" })}
          onSubmit={async (title) => void (await add.run({ title }))}
        />
      </Section>
      <Section title="Recent">
        <RecordTable<RecordRow<Item>>
          caption="Recent items"
          columns={[
            { id: "title", header: "Title", cell: (r) => r.values.title },
            { id: "day", header: "Day", cell: (r) => formatDay(r.values.noted_on) },
          ]}
          rows={recent.records}
          getRowId={(r) => r.id}
          loading={recent.loading}
          error={recent.error}
          onRetry={recent.refresh}
          empty={{ title: "No items yet", message: "Add the first one above." }}
        />
      </Section>
    </Page>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AlphaApp>
      <App />
    </AlphaApp>
  </StrictMode>,
);

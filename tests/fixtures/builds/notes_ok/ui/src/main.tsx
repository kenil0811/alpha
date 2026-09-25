// Neutral fixture screen: quick entry plus the latest notes.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import { AlphaApp, Page, QuickEntry, RecordTable, Section, formatDay, useAction, useView, type RecordRow } from "@alpha/ui-kit";

type Note = { title: string; noted_on: string };

function App() {
  const add = useAction("add_note");
  const recent = useView<Note>("notes.recent", { limit: 20 });
  return (
    <Page title="Notes" description="Write a note and see the latest ones.">
      <Section title="Add">
        <QuickEntry
          label="Note"
          parse={(text) => (text.trim() ? { status: "ok", value: text.trim(), summary: text.trim() } : { status: "empty" })}
          onSubmit={async (title) => void (await add.run({ title }))}
        />
      </Section>
      <Section title="Latest">
        <RecordTable<RecordRow<Note>>
          caption="Latest notes"
          columns={[
            { id: "title", header: "Note", cell: (r) => r.values.title },
            { id: "day", header: "Day", cell: (r) => formatDay(r.values.noted_on) },
          ]}
          rows={recent.records}
          getRowId={(r) => r.id}
          loading={recent.loading}
          error={recent.error}
          onRetry={recent.refresh}
          empty={{ title: "No notes yet", message: "Write the first one above." }}
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

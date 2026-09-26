import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import {
  AlphaApp,
  Badge,
  Button,
  Cluster,
  DateField,
  DetailDrawer,
  DetailList,
  Form,
  OperationStatus,
  Page,
  RecordTable,
  Section,
  SelectField,
  Stack,
  TextAreaField,
  TextField,
  eq,
  formatDay,
  orderBy,
  today,
  useAction,
  useView,
  type RecordRow,
} from "@alpha/ui-kit";

type Opening = {
  company: string;
  role: string;
  where_i_found_it: string | null;
  link: string | null;
  stage: string;
  date_found: string;
  notes: string | null;
  last_activity: string | null;
};

type Step = {
  opening: string;
  date: string;
  what_i_did: string;
  note: string | null;
};

const STAGES = ["Found", "Applied", "Interviewing", "Offer", "Rejected", "Withdrew"];

const STEPS = [
  "Found it",
  "Applied",
  "Emailed recruiter",
  "Phone screen",
  "Interviewed",
  "Offer received",
  "Rejected",
  "Withdrew",
  "Stage changed",
  "Other note",
];

const ALL = "All stages";

function AddOpening() {
  const add = useAction("add_opening");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [source, setSource] = useState("");
  const [link, setLink] = useState("");
  const [notes, setNotes] = useState("");

  return (
    <Form
      label="Add an opening"
      onSubmit={async () => {
        try {
          await add.run({
            company,
            role,
            where_i_found_it: source,
            link,
            notes,
          });
          setCompany("");
          setRole("");
          setSource("");
          setLink("");
          setNotes("");
        } catch {
          /* OperationStatus explains it; the typed input stays so it can be saved again */
        }
      }}
    >
      <Stack>
        <TextField label="Company" required value={company} onChange={setCompany} />
        <TextField label="Role" required value={role} onChange={setRole} />
        <TextField label="Where I found it" value={source} onChange={setSource} />
        <TextField label="Link" value={link} onChange={setLink} hint="Pasted as plain text." />
        <TextAreaField label="Notes" value={notes} onChange={setNotes} />
        <Cluster>
          <Button type="submit" variant="primary" busy={add.state === "saving"} busyLabel="Saving…">
            Add opening
          </Button>
        </Cluster>
        <OperationStatus state={add.state} error={add.error} />
      </Stack>
    </Form>
  );
}

function OpeningDetail({ row, onClose }: { row: RecordRow<Opening>; onClose: () => void }) {
  const logStep = useAction("log_step");
  const setStage = useAction("set_stage");
  const history = useView<Step>("steps_taken.for_opening", {
    where: eq("opening", row.id),
    limit: 50,
  });
  const [date, setDate] = useState(today());
  const [whatIDid, setWhatIDid] = useState("Applied");
  const [note, setNote] = useState("");
  const [stage, setNewStage] = useState(row.values.stage);

  return (
    <DetailDrawer
      open
      onClose={onClose}
      title={row.values.company + " — " + row.values.role}
      description={"Stage: " + row.values.stage}
    >
      <Stack>
        <DetailList
          items={[
            { label: "Where I found it", value: row.values.where_i_found_it ?? "Not recorded" },
            { label: "Link", value: row.values.link ?? "None saved" },
            { label: "Date found", value: formatDay(row.values.date_found) },
            { label: "Notes", value: row.values.notes ?? "None" },
          ]}
        />
        <Section title="Log a step">
          <Form
            label="Log a step"
            onSubmit={async () => {
              try {
                await logStep.run({
                  opening: row.id,
                  date,
                  what_i_did: whatIDid,
                  note,
                });
                setNote("");
                history.refresh();
              } catch {
                /* OperationStatus explains it; the typed input stays */
              }
            }}
          >
            <Stack>
              <DateField label="Date" required value={date} onChange={setDate} />
              <SelectField
                label="What I did"
                required
                value={whatIDid}
                onChange={setWhatIDid}
                options={STEPS.map((step) => ({ value: step, label: step }))}
              />
              <TextField label="Note" value={note} onChange={setNote} />
              <Cluster>
                <Button
                  type="submit"
                  variant="primary"
                  busy={logStep.state === "saving"}
                  busyLabel="Saving…"
                >
                  Log step
                </Button>
              </Cluster>
              <OperationStatus state={logStep.state} error={logStep.error} />
            </Stack>
          </Form>
        </Section>
        <Section title="Change the stage">
          <Form
            label="Change the stage"
            onSubmit={async () => {
              try {
                await setStage.run({ opening: row.id, new_stage: stage });
                history.refresh();
              } catch {
                /* OperationStatus explains it */
              }
            }}
          >
            <Stack>
              <SelectField
                label="Stage"
                required
                value={stage}
                onChange={setNewStage}
                options={STAGES.map((name) => ({ value: name, label: name }))}
              />
              <Cluster>
                <Button
                  type="submit"
                  variant="secondary"
                  busy={setStage.state === "saving"}
                  busyLabel="Saving…"
                >
                  Change stage
                </Button>
              </Cluster>
              <OperationStatus state={setStage.state} error={setStage.error} />
            </Stack>
          </Form>
        </Section>
        <Section title="History">
          <RecordTable<RecordRow<Step>>
            caption="Steps taken on this opening"
            columns={[
              { id: "what", header: "What I did", cell: (r) => r.values.what_i_did },
              { id: "date", header: "Date", cell: (r) => formatDay(r.values.date) },
              { id: "note", header: "Note", cell: (r) => r.values.note ?? "" },
            ]}
            rows={history.records}
            getRowId={(r) => r.id}
            loading={history.loading}
            error={history.error}
            onRetry={history.refresh}
            empty={{ title: "No steps yet", message: "Log the first step above." }}
          />
        </Section>
      </Stack>
    </DetailDrawer>
  );
}

function App() {
  const [filter, setFilter] = useState(ALL);
  const [openId, setOpenId] = useState<string | null>(null);
  const openings = useView<Opening>("job_openings.list", {
    where: filter === ALL ? undefined : eq("stage", filter),
    order_by: orderBy("-last_activity", "-created_at"),
    limit: 100,
  });
  const everything = useView<Opening>("job_openings.list", { limit: 100 });

  const label = (name: string) => {
    if (everything.loading || everything.error) return name;
    return name + " (" + everything.records.filter((r) => r.values.stage === name).length + ")";
  };
  const opened = openings.records.find((r) => r.id === openId) ?? null;

  return (
    <Page
      title="Job Opening Tracker"
      description="Add an opening, log each step you take on it, and see which openings are at which stage."
    >
      <Section title="Add an opening">
        <AddOpening />
      </Section>
      <Section title="My openings" description="Newest activity first.">
        <Stack>
          <Cluster>
            <Button
              variant={filter === ALL ? "primary" : "ghost"}
              small
              onClick={() => setFilter(ALL)}
            >
              {ALL}
            </Button>
            {STAGES.map((name) => (
              <Button
                key={name}
                variant={filter === name ? "primary" : "ghost"}
                small
                onClick={() => setFilter(name)}
              >
                {label(name)}
              </Button>
            ))}
          </Cluster>
          <RecordTable<RecordRow<Opening>>
            caption="Openings I am tracking"
            columns={[
              { id: "company", header: "Company", cell: (r) => r.values.company },
              { id: "role", header: "Role", cell: (r) => r.values.role },
              {
                id: "stage",
                header: "Stage",
                cell: (r) => <Badge tone="info">{r.values.stage}</Badge>,
              },
              {
                id: "source",
                header: "Where I found it",
                cell: (r) => r.values.where_i_found_it ?? "Not recorded",
              },
              { id: "found", header: "Date found", cell: (r) => formatDay(r.values.date_found) },
            ]}
            rows={openings.records}
            getRowId={(r) => r.id}
            getRowLabel={(r) => r.values.company + " — " + r.values.role}
            onOpen={(r) => setOpenId(r.id)}
            loading={openings.loading}
            error={openings.error}
            onRetry={openings.refresh}
            empty={{
              title: "No openings here yet",
              message: "Add an opening above, or choose another stage.",
            }}
          />
        </Stack>
      </Section>
      {opened ? <OpeningDetail row={opened} onClose={() => setOpenId(null)} /> : null}
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

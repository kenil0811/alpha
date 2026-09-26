import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import {
  AlphaApp,
  Button,
  Cluster,
  DateField,
  DetailDrawer,
  DetailList,
  Form,
  OperationStatus,
  Page,
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
          await add.run({ company, role, where_i_found_it: source, link, notes });
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
        <TextField
          label="Company"
          required
          value={company}
          onChange={(event) => setCompany(event.target.value)}
        />
        <TextField
          label="Role"
          required
          value={role}
          onChange={(event) => setRole(event.target.value)}
        />
        <TextField
          label="Where I found it"
          value={source}
          onChange={(event) => setSource(event.target.value)}
        />
        <TextField
          label="Link"
          hint="Pasted as plain text."
          value={link}
          onChange={(event) => setLink(event.target.value)}
        />
        <TextAreaField
          label="Notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
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
  const changeStage = useAction("set_stage");
  const history = useView<Step>("steps_taken.for_opening", {
    where: eq("opening", row.id),
    limit: 100,
  });
  const [date, setDate] = useState<string>(today());
  const [whatIDid, setWhatIDid] = useState("Applied");
  const [note, setNote] = useState("");
  const [stage, setStage] = useState<string>(row.values.stage);

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
                await logStep.run({ opening: row.id, date, what_i_did: whatIDid, note });
                setNote("");
                history.refresh();
              } catch {
                /* OperationStatus explains it; the typed input stays */
              }
            }}
          >
            <Stack>
              <DateField
                label="Date"
                required
                value={date}
                onChange={(event) => setDate(event.target.value)}
              />
              <SelectField
                label="What I did"
                required
                value={whatIDid}
                onChange={(event) => setWhatIDid(event.target.value)}
                options={STEPS.map((step) => ({ value: step, label: step }))}
              />
              <TextField
                label="Note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
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
                await changeStage.run({ opening: row.id, new_stage: stage });
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
                onChange={(event) => setStage(event.target.value)}
                options={STAGES.map((name) => ({ value: name, label: name }))}
              />
              <Cluster>
                <Button
                  type="submit"
                  variant="secondary"
                  busy={changeStage.state === "saving"}
                  busyLabel="Saving…"
                >
                  Change stage
                </Button>
              </Cluster>
              <OperationStatus state={changeStage.state} error={changeStage.error} />
            </Stack>
          </Form>
        </Section>
        <Section title="History">
          {history.error ? (
            <div role="alert">Sorry — this history could not be loaded just now.</div>
          ) : history.loading ? (
            <p>Loading the history…</p>
          ) : history.records.length === 0 ? (
            <p>No steps logged yet. Log the first one above.</p>
          ) : (
            <DetailList
              items={history.records.map((step) => ({
                label: formatDay(step.values.date) + " — " + step.values.what_i_did,
                value: step.values.note ?? "",
              }))}
            />
          )}
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

  const countLabel = (name: string) => {
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
                {countLabel(name)}
              </Button>
            ))}
          </Cluster>
          {openings.error ? (
            <div role="alert">
              <Stack>
                <span>Sorry — your openings could not be loaded just now.</span>
                <Cluster>
                  <Button small variant="secondary" onClick={() => openings.refresh()}>
                    Try again
                  </Button>
                </Cluster>
              </Stack>
            </div>
          ) : openings.loading ? (
            <p>Loading your openings…</p>
          ) : openings.records.length === 0 ? (
            <p>No openings here yet. Add one above, or choose another stage.</p>
          ) : (
            <Stack>
              {openings.records.map((row) => (
                <div key={row.id}>
                  <Stack>
                    <h3>{row.values.company + " — " + row.values.role}</h3>
                    <DetailList
                      items={[
                        { label: "Stage", value: row.values.stage },
                        { label: "Role", value: row.values.role },
                        {
                          label: "Where I found it",
                          value: row.values.where_i_found_it ?? "Not recorded",
                        },
                        { label: "Date found", value: formatDay(row.values.date_found) },
                      ]}
                    />
                    <Cluster>
                      <Button small variant="secondary" onClick={() => setOpenId(row.id)}>
                        Open
                      </Button>
                    </Cluster>
                  </Stack>
                </div>
              ))}
            </Stack>
          )}
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

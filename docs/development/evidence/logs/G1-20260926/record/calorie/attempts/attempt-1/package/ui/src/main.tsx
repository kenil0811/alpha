// Daily Food Log: add what you ate, see the day's total, browse past days, watch the trend.
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import {
  AlphaApp,
  Button,
  Cluster,
  DateField,
  DetailDrawer,
  Form,
  MetricCard,
  OperationStatus,
  Page,
  RecordTable,
  Section,
  Stack,
  TextField,
  TrendChart,
  eq,
  formatDay,
  useAction,
  useAggregate,
  useView,
  type RecordRow,
} from "@alpha/ui-kit";

type Entry = {
  when: string;
  eaten_at: string | null;
  food: string;
  amount: string;
  calories: number;
  calories_are_estimate: boolean | null;
  meal: string | null;
};
type Row = RecordRow<Entry>;

const MEALS = ["breakfast", "lunch", "dinner", "snack"];

function pad(value: number): string {
  return value < 10 ? `0${value}` : `${value}`;
}

function dayOf(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function todayDay(): string {
  return dayOf(new Date());
}

function shiftDay(day: string, byDays: number): string {
  const parts = day.split("-");
  const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  date.setDate(date.getDate() + byDays);
  return dayOf(date);
}

function mealName(meal: string | null): string {
  if (!meal) return "No meal label";
  return meal.charAt(0).toUpperCase() + meal.slice(1);
}

function App() {
  const [day, setDay] = useState(todayDay());
  const [food, setFood] = useState("");
  const [amount, setAmount] = useState("");
  const [calories, setCalories] = useState("");
  const [meal, setMeal] = useState("");
  const [isEstimate, setIsEstimate] = useState(false);
  const [caloriesProblem, setCaloriesProblem] = useState("");
  const [span, setSpan] = useState(7);
  const [editing, setEditing] = useState<Row | null>(null);
  const [draft, setDraft] = useState<Entry & { caloriesText: string }>({
    when: todayDay(),
    eaten_at: "",
    food: "",
    amount: "",
    calories: 0,
    calories_are_estimate: false,
    meal: "",
    caloriesText: "",
  });

  const estimate = useAction("estimate_calories");
  const add = useAction("log_entry");
  const fix = useAction("correct_entry");

  const entries = useView<Entry>("food_entries.by_day", { where: eq("when", day), limit: 100 });
  const perDay = useAggregate("food_entries.daily", undefined as any);

  // The estimate lands in the Calories box, where it can be replaced.
  useEffect(() => {
    const output: any = estimate.output;
    if (output && output.estimated_calories !== undefined && output.estimated_calories !== null) {
      const guessed = Math.round(Number(output.estimated_calories));
      if (!Number.isNaN(guessed)) {
        setCalories(`${guessed}`);
        setIsEstimate(true);
        setCaloriesProblem("");
      }
    }
  }, [estimate.output]);

  const rows = entries.records;
  const dayTotal = rows.reduce((sum, row) => sum + Number(row.values.calories ?? 0), 0);
  const isToday = day === todayDay();

  async function addEntry() {
    const typed = calories.trim();
    if (typed !== "" && Number.isNaN(Number(typed))) {
      setCaloriesProblem("Enter a number, or leave it blank for an estimate.");
      return;
    }
    setCaloriesProblem("");
    const input: any = { food: food.trim(), amount: amount.trim(), when: day };
    // A number the person typed is theirs; an untouched estimate is estimated again on saving.
    if (typed !== "" && !isEstimate) input.calories = Number(typed);
    if (meal) input.meal = meal;
    try {
      await add.run(input);
      setFood("");
      setAmount("");
      setCalories("");
      setMeal("");
      setIsEstimate(false);
      estimate.reset();
    } catch {
      // OperationStatus says what went wrong; the typed entry stays so it can be saved again.
    }
  }

  async function askEstimate() {
    if (!food.trim() || !amount.trim()) {
      setCaloriesProblem("Fill in the food and the amount first.");
      return;
    }
    setCaloriesProblem("");
    try {
      await estimate.run({ food: food.trim(), amount: amount.trim() });
    } catch {
      // OperationStatus explains; a number can still be typed by hand.
    }
  }

  function openEntry(row: Row) {
    setEditing(row);
    setDraft({
      when: row.values.when,
      eaten_at: row.values.eaten_at ?? "",
      food: row.values.food,
      amount: row.values.amount,
      calories: Number(row.values.calories ?? 0),
      calories_are_estimate: Boolean(row.values.calories_are_estimate),
      meal: row.values.meal ?? "",
      caloriesText: `${row.values.calories ?? ""}`,
    });
  }

  async function saveEdit() {
    if (!editing) return;
    const typed = draft.caloriesText.trim();
    const input: any = {
      entry: editing.id,
      food: draft.food.trim(),
      amount: draft.amount.trim(),
      when: draft.when,
      eaten_at: draft.eaten_at ?? "",
      meal: draft.meal ?? "",
    };
    if (typed !== "" && !Number.isNaN(Number(typed))) input.calories = Number(typed);
    try {
      await fix.run(input);
      setDay(draft.when);
      setEditing(null);
    } catch {
      // OperationStatus explains; the changes stay on screen.
    }
  }

  async function removeEntry() {
    if (!editing) return;
    try {
      await fix.run({ entry: editing.id, delete: true });
      setEditing(null);
    } catch {
      // OperationStatus explains; nothing was removed.
    }
  }

  const totalsByDay: Record<string, number> = {};
  for (const group of (perDay.groups ?? []) as any[]) {
    const key: any = group?.key ?? {};
    const groupDay = String(key.when ?? key.when_day ?? "");
    if (groupDay) totalsByDay[groupDay.slice(0, 10)] = Number(group?.values?.total ?? 0);
  }
  const firstDay = shiftDay(todayDay(), -(span - 1));
  const points: any[] = [];
  let spanTotal = 0;
  let daysLogged = 0;
  for (let step = 0; step < span; step += 1) {
    const pointDay = shiftDay(firstDay, step);
    const logged = Object.prototype.hasOwnProperty.call(totalsByDay, pointDay);
    const value = logged ? totalsByDay[pointDay] ?? 0 : null;
    if (logged) {
      spanTotal += Number(value ?? 0);
      daysLogged += 1;
    }
    points.push({ day: pointDay, date: pointDay, label: formatDay(pointDay), value, total: value });
  }
  const average = daysLogged > 0 ? Math.round(spanTotal / span) : null;

  return (
    <Page
      title="Daily Food Log"
      description="Write down what you ate and how much. Calories can be estimated for you, and you can always type your own."
    >
      <Section title={isToday ? "Add what you ate today" : `Add an entry for ${formatDay(day)}`}>
        <Form
          label="Add an entry"
          onSubmit={async () => {
            await addEntry();
          }}
        >
          <Stack>
            <TextField
              label="Food"
              value={food}
              onChange={(value: any) => setFood(typeof value === "string" ? value : value?.target?.value ?? "")}
              hint="What you ate, for example 2 rotis and dal."
              required
            />
            <TextField
              label="Amount"
              value={amount}
              onChange={(value: any) => setAmount(typeof value === "string" ? value : value?.target?.value ?? "")}
              hint="How much you ate, for example 1 bowl — calories depend on it."
              required
            />
            <TextField
              label="Calories"
              value={calories}
              onChange={(value: any) => {
                setCalories(typeof value === "string" ? value : value?.target?.value ?? "");
                setIsEstimate(false);
                setCaloriesProblem("");
              }}
              hint={
                isEstimate
                  ? "This number is an estimate from your description — type over it to use your own."
                  : "Leave it blank and Alpha estimates it for you."
              }
              error={caloriesProblem ? caloriesProblem : undefined}
            />
            <Cluster>
              {MEALS.map((name) => (
                <Button
                  key={name}
                  type="button"
                  small
                  variant={meal === name ? "primary" : "secondary"}
                  onClick={() => setMeal(meal === name ? "" : name)}
                >
                  {mealName(name)}
                </Button>
              ))}
            </Cluster>
            <Cluster>
              <Button type="submit" variant="primary" busy={add.state === "saving"} busyLabel="Saving…">
                Add entry
              </Button>
              <Button
                type="button"
                variant="secondary"
                busy={estimate.state === "saving"}
                busyLabel="Estimating…"
                onClick={askEstimate}
              >
                Estimate calories
              </Button>
            </Cluster>
            <OperationStatus state={add.state} error={add.error} />
            <OperationStatus state={estimate.state} error={estimate.error} />
          </Stack>
        </Form>
      </Section>

      <Section
        title={isToday ? "Today" : formatDay(day)}
        description="Open an entry to fix the food, amount, time, meal or calories, or to remove it."
      >
        <Stack>
          <Cluster>
            <Button type="button" variant="secondary" onClick={() => setDay(shiftDay(day, -1))}>
              Earlier day
            </Button>
            <Button type="button" variant="secondary" onClick={() => setDay(shiftDay(day, 1))}>
              Later day
            </Button>
            <Button type="button" variant="ghost" onClick={() => setDay(todayDay())}>
              Back to today
            </Button>
          </Cluster>
          <DateField
            label="Day"
            value={day}
            onChange={(value: any) => {
              const next = typeof value === "string" ? value : value?.target?.value ?? "";
              if (next) setDay(next);
            }}
          />
          <MetricCard
            label={isToday ? "Total for today" : `Total for ${formatDay(day)}`}
            value={rows.length > 0 ? dayTotal : null}
            unit="kcal"
            hint={`${rows.length} ${rows.length === 1 ? "entry" : "entries"} logged`}
          />
          <RecordTable<Row>
            caption={`What you ate on ${formatDay(day)}`}
            columns={[
              { id: "food", header: "Food", cell: (row) => row.values.food },
              { id: "amount", header: "Amount", cell: (row) => row.values.amount },
              {
                id: "calories",
                header: "Calories",
                cell: (row) =>
                  `${row.values.calories ?? ""}${row.values.calories_are_estimate ? " (estimate)" : ""}`,
              },
              { id: "time", header: "Time", cell: (row) => row.values.eaten_at ?? "No time" },
              { id: "meal", header: "Meal", cell: (row) => mealName(row.values.meal) },
            ]}
            rows={rows}
            getRowId={(row) => row.id}
            getRowLabel={(row) => row.values.food}
            onOpen={openEntry}
            loading={entries.loading}
            error={entries.error}
            onRetry={entries.refresh}
            empty={{
              title: "Nothing logged for this day",
              message: "Add what you ate using the fields above.",
            }}
          />
        </Stack>
      </Section>

      <Section title="Trends" description="Daily calories, with the average per day over the range.">
        <Stack>
          <Cluster>
            <Button
              type="button"
              variant={span === 7 ? "primary" : "secondary"}
              onClick={() => setSpan(7)}
            >
              Last 7 days
            </Button>
            <Button
              type="button"
              variant={span === 30 ? "primary" : "secondary"}
              onClick={() => setSpan(30)}
            >
              Last 30 days
            </Button>
          </Cluster>
          <Cluster>
            <MetricCard label="Average per day" value={average} unit="kcal" hint={`Over ${span} days`} />
            <MetricCard
              label="Days with entries"
              value={daysLogged}
              hint={`Out of the last ${span} days`}
            />
          </Cluster>
          <TrendChart title={`Daily calories, last ${span} days`} points={points} unit="kcal" />
        </Stack>
      </Section>

      {editing ? (
        <DetailDrawer
          open
          onClose={() => setEditing(null)}
          title={`Fix "${editing.values.food}"`}
          description={
            editing.values.calories_are_estimate
              ? "These calories are an estimate. Typing your own number replaces it."
              : "Change anything that is wrong, or remove the entry."
          }
        >
          <Form
            label="Fix this entry"
            onSubmit={async () => {
              await saveEdit();
            }}
          >
            <Stack>
              <TextField
                label="Food"
                value={draft.food}
                onChange={(value: any) =>
                  setDraft({
                    ...draft,
                    food: typeof value === "string" ? value : value?.target?.value ?? "",
                  })
                }
                required
              />
              <TextField
                label="Amount"
                value={draft.amount}
                onChange={(value: any) =>
                  setDraft({
                    ...draft,
                    amount: typeof value === "string" ? value : value?.target?.value ?? "",
                  })
                }
                required
              />
              <TextField
                label="Calories"
                value={draft.caloriesText}
                onChange={(value: any) =>
                  setDraft({
                    ...draft,
                    caloriesText: typeof value === "string" ? value : value?.target?.value ?? "",
                  })
                }
                hint={
                  draft.calories_are_estimate
                    ? "Currently an estimate — your number replaces it."
                    : "Your own number."
                }
              />
              <TextField
                label="Time"
                value={draft.eaten_at ?? ""}
                onChange={(value: any) =>
                  setDraft({
                    ...draft,
                    eaten_at: typeof value === "string" ? value : value?.target?.value ?? "",
                  })
                }
                hint="Like 13:30"
              />
              <DateField
                label="Day"
                value={draft.when}
                onChange={(value: any) => {
                  const next = typeof value === "string" ? value : value?.target?.value ?? "";
                  if (next) setDraft({ ...draft, when: next });
                }}
              />
              <Cluster>
                {MEALS.map((name) => (
                  <Button
                    key={name}
                    type="button"
                    small
                    variant={draft.meal === name ? "primary" : "secondary"}
                    onClick={() => setDraft({ ...draft, meal: draft.meal === name ? "" : name })}
                  >
                    {mealName(name)}
                  </Button>
                ))}
              </Cluster>
              <Cluster>
                <Button type="submit" variant="primary" busy={fix.state === "saving"} busyLabel="Saving…">
                  Save changes
                </Button>
                <Button type="button" variant="danger" onClick={removeEntry}>
                  Delete entry
                </Button>
              </Cluster>
              <OperationStatus state={fix.state} error={fix.error} />
            </Stack>
          </Form>
        </DetailDrawer>
      ) : null}
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

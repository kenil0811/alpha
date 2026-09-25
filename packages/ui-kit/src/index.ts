/**
 * @alpha/ui-kit — the interaction kit generated App UI composes. See REFERENCE.md.
 * Import the styles once from the App entry: `import "@alpha/ui-kit/styles.css";`
 */
export { Page, Section, Stack, Cluster, Columns, VisuallyHidden, cx } from "./components/layout";
export type { PageProps, SectionProps } from "./components/layout";
export {
  Button,
  Field,
  TextField,
  NumberField,
  DateField,
  SelectField,
  TextAreaField,
  CheckboxField,
  parseNumber,
} from "./components/controls";
export type { ButtonProps, ButtonVariant, FieldProps, FieldControlProps, NumberFieldProps, SelectFieldProps, SelectOption } from "./components/controls";
export { StatusMessage, Badge, EmptyState, LoadingState, ErrorState, OperationStatus, ProvenanceNote } from "./components/feedback";
export type { Tone, SaveState, FieldProvenance } from "./components/feedback";
export { Form, useFormSubmit } from "./components/Form";
export type { FormProps } from "./components/Form";
export { QuickEntry } from "./components/QuickEntry";
export type { QuickEntryProps, QuickEntryOutcome, ParseResult } from "./components/QuickEntry";
export { FilterBar } from "./components/FilterBar";
export type { FilterBarProps, FilterDefinition, FilterValues } from "./components/FilterBar";
export { RecordTable, Pager } from "./components/RecordTable";
export type { Column, SortState, RecordTableProps, PagerProps } from "./components/RecordTable";
export { DetailDrawer, DetailList } from "./components/DetailDrawer";
export type { DetailDrawerProps } from "./components/DetailDrawer";
export { ReviewQueue } from "./components/ReviewQueue";
export type { ReviewQueueProps, ReviewDecision } from "./components/ReviewQueue";
export { MetricCard, TrendChart, RangeSelect } from "./components/Trend";
export type { MetricCardProps, TrendChartProps } from "./components/Trend";
export { AlphaApp, AlphaProvider, useAlpha, useView, useAggregate, useAction, friendlyError, ActionFailed } from "./data/hooks";
export type { RecordRow, AggregateGroup, ViewQuery, ViewState, AggregateState, ActionState, DataClient, FieldProvenanceData } from "./data/hooks";
export { eq, ne, lt, lte, gt, gte, oneOf, contains, startsWith, isEmpty, not, allOf, anyOf, orderBy } from "./data/query";
export type { FilterNode, FilterOp, SortKey } from "./data/query";
export { formatNumber, formatWithUnit, formatDay, today, addDays, daySeries } from "./format";
export type { DayPoint } from "./format";

export const KIT_VERSION = "0.1.0";

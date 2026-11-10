import { useFieldValue } from "react-admin";

export interface DurationFieldProps {
  /** the attribute of the record which answers the seconds */
  source: string;
}

/** the duration in the language-neutral clock form, with days when it holds them */
const formatDuration = (seconds: number): string => {
  const total = Math.round(seconds);
  const days = Math.floor(total / 86400);
  const rest = total % 86400;
  const hhmmss = [
    Math.floor(rest / 3600),
    Math.floor(rest / 60) % 60,
    rest % 60,
  ]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
  return days > 0 ? `${days} d ${hhmmss}` : hhmmss;
};

/**
 * The time a decided background process needed until its decision, as
 * seconds of the record in a clock form.
 *
 * The api answers the seconds between the creation and the decision of a
 * process, the waiting, retry and scheduling intervals of its tasks
 * included - the number reads as "how long the request waited for its
 * decision", not as the time the work spent running. It is rendered here
 * as the clock form the operation itself would have shown ("1 d 02:03:04"
 * or "02:03:04"), without inventing a precision the timestamps do not
 * have. Nothing is shown for a process which did not decide about itself
 * yet: the time until a running process decides is not known, not zero.
 */
const DurationField = ({ source }: DurationFieldProps) => {
  const seconds = useFieldValue({ source });
  if (typeof seconds !== "number" || Number.isNaN(seconds)) {
    return null;
  }
  return <span>{formatDuration(seconds)}</span>;
};

export default DurationField;

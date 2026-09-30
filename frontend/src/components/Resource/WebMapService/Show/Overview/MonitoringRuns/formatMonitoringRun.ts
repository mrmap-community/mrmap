import { format, isToday, isYesterday } from "date-fns";

export const getDuration = (dateCreated: string, dateDone?: string) => {
  const created = new Date(dateCreated);
  return dateDone
    ? (new Date(dateDone).getTime() - created.getTime()) / 1000
    : undefined;
};

export const formatMonitoringRun = (dateCreated: string, dateDone?: string) => {
  const created = new Date(dateCreated);

  const dateLabel = isToday(created)
    ? "Today"
    : isYesterday(created)
      ? "Yesterday"
      : format(created, "dd.MM.yyyy");

  const timeLabel = format(created, "HH:mm");

  const duration = getDuration(dateCreated, dateDone);

  return `${dateLabel}, ${timeLabel}${
    duration !== undefined ? ` · ${duration.toFixed(2)} s` : ""
  }`;
};

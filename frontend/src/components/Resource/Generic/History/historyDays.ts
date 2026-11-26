/** the days of the past the chart of a resource counts the changes of */
export const CHANGE_DAYS = 30;

/**
 * The day a statistic of the api belongs to, as the chart asks it back.
 *
 * The api answers the day of the resource as a plain day of the month, and a day
 * of the month is never moved into another day by the timezone of the viewer, so
 * an answered day is taken as it is and only an instant is read as a day.
 */
const dayOf = (day: unknown) => {
  if (typeof day === 'string') return day.slice(0, 10);
  const date = new Date(day as string | number);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
};

/** the given amount of days before today, oldest first, as yyyy-mm-dd */
export const lastDays = (days: number): string[] => {
  const today = new Date();
  return Array.from({ length: days }, (_unused, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (days - 1 - index));
    return dayOf(date);
  });
};

/** the changes of one day of the window of the chart */
export interface DailyChange {
  /** the day the change belongs to, as yyyy-mm-dd */
  id: string
  /** what was added to the inventory of the resource that day */
  new: number
  /** what was updated in the inventory of the resource that day */
  updated: number
  /** what was taken out of the inventory of the resource that day */
  deleted: number
  /** the inventory the resource counted that day */
  total: number
}

/**
 * The changes of the given days, oldest first, and the inventory which was
 * answered for the day after them.
 *
 * The api answers only the days which did have a change, so a day without an
 * answer is a day without any change and never a hole. The inventory of the
 * oldest day is stepped back from the inventory of today, because the api
 * answers the changes per day and not the inventory per day.
 *
 * @param data the statistics the api answered for the resource
 * @param total the inventory the resource counts today
 * @param days the days of the window, oldest first, as yyyy-mm-dd
 * @returns the changes of every day of the window, oldest first
 */
export const changesOfDays = (
  data: import("react-admin").RaRecord[] | undefined,
  total: number,
  days: string[]
): DailyChange[] => {
  const byDay = new Map<string, import("react-admin").RaRecord>();
  data?.forEach(record => byDay.set(dayOf(record?.day), record));

  const changes = days.map(day => {
    const answered = byDay.get(day);
    return {
      id: day,
      new: answered?.new ?? 0,
      updated: answered?.updated ?? 0,
      deleted: answered?.deleted ?? 0,
      total: 0,
    };
  });

  // the last day of the window carries the inventory the resource counts today
  let inventory = total;
  for (let index = changes.length - 1; index >= 0; index--) {
    changes[index].total = inventory;
    inventory = inventory - changes[index].new + changes[index].deleted;
  }

  return changes;
}

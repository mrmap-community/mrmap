import { describe, expect, it } from "vitest";

import readCron from "./cronReading";

describe("readCron", () => {
  it("names the rhythm which lets everything through", () => {
    expect(readCron("* * * * *")).toEqual({ key: "everyMinute" });
  });

  it("names the steps of minutes and of hours", () => {
    expect(readCron("*/15 * * * *")).toEqual({
      key: "everyNMinutes",
      every: 15,
    });
    expect(readCron("0 */6 * * *")).toEqual({
      key: "everyNHours",
      every: 6,
      minute: 0,
    });
  });

  it("names the hour which runs once and the day which runs at a time", () => {
    expect(readCron("20 * * * *")).toEqual({ key: "hourly", minute: 20 });
    expect(readCron("30 2 * * *")).toEqual({ key: "daily", time: "02:30" });
    expect(readCron("  30   2  * * *  ")).toEqual({
      key: "daily",
      time: "02:30",
    });
  });

  it("names the weekdays, the day of the month and the month", () => {
    expect(readCron("0 3 * * 1,5")).toEqual({
      key: "weekly",
      weekdays: [1, 5],
      time: "03:00",
    });
    expect(readCron("0 0 15 * *")).toEqual({
      key: "monthly",
      dayOfMonth: 15,
      time: "00:00",
    });
    expect(readCron("0 0 1 12 *")).toEqual({
      key: "yearly",
      dayOfMonth: 1,
      month: 12,
      time: "00:00",
    });
  });

  it("reads nothing for an expression it would only guess at", () => {
    // a range of days, a list of minutes, an expression of another length and
    // no expression at all - the row keeps the raw expression for these
    expect(readCron("0 3 1-5 * *")).toBeUndefined();
    expect(readCron("0,30 2 * * *")).toBeUndefined();
    // an hour which does not exist is no rhythm either
    expect(readCron("0 25 * * *")).toBeUndefined();
    expect(readCron("30 2")).toBeUndefined();
    expect(readCron("")).toBeUndefined();
    expect(readCron(null)).toBeUndefined();
    expect(readCron(undefined)).toBeUndefined();
  });
});

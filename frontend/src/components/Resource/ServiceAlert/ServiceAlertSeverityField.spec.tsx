import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ServiceAlertSeverityField from "./ServiceAlertSeverityField";

const state = vi.hoisted(() => ({
  severity: undefined as string | undefined,
}));

vi.mock("react-admin", () => ({
  useFieldValue: () => state.severity,
  useTranslate: () => (key: string) => key,
}));

describe("ServiceAlertSeverityField", () => {
  beforeEach(() => {
    state.severity = undefined;
  });

  it("names the severity of the alert the record reports", () => {
    for (const severity of ["error", "warning"]) {
      state.severity = severity;
      const { unmount } = render(<ServiceAlertSeverityField />);
      expect(
        screen.getByText(`serviceAlerts.severity.${severity}`),
      ).toBeDefined();
      unmount();
    }
  });

  it("answers nothing for an alert without a severity", () => {
    render(<ServiceAlertSeverityField />);
    expect(screen.queryByText(/serviceAlerts\.severity/)).toBeNull();
  });
});

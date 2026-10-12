import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ServiceAlertCategoryField from "./ServiceAlertCategoryField";

const state = vi.hoisted(() => ({
  category: undefined as string | undefined,
}));

vi.mock("react-admin", () => ({
  useFieldValue: () => state.category,
  useTranslate: () => (key: string) => key,
}));

describe("ServiceAlertCategoryField", () => {
  beforeEach(() => {
    state.category = undefined;
  });

  it("translates the state the alert reports", () => {
    state.category = "monitoring_failed";
    render(<ServiceAlertCategoryField />);
    expect(screen.getByText("serviceAlerts.category.monitoring_failed")).toBeDefined();
  });

  it("keeps the name of the state the api answered readable", () => {
    state.category = "harvesting_incomplete";
    render(<ServiceAlertCategoryField />);
    expect(screen.getByText(/serviceAlerts/).getAttribute("data-category")).toBe(
      "harvesting_incomplete",
    );
  });

  it("answers nothing for an alert without a category", () => {
    render(<ServiceAlertCategoryField />);
    expect(screen.queryByText(/serviceAlerts\.category/)).toBeNull();
  });
});

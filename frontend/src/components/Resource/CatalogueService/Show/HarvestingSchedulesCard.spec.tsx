import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useListContext } from "react-admin";
import { HarvestingSchedulesCardBase } from "./HarvestingSchedulesCard";

vi.mock("./RunHarvestingButton", () => ({
  default: () => <span>Harvest now</span>,
}));

vi.mock("react-admin", () => ({
  Button: ({ to, label }: { to: string; label: string }) => (
    <a href={to}>{label}</a>
  ),
  Loading: () => <span>Loading</span>,
  SimpleList: () => null,
  useListContext: vi.fn(),
  useRecordContext: () => ({ id: "csw-1" }),
  useTranslate: () => (key: string) => key,
}));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: () => null,
}));
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: () => ({}),
}));
beforeEach(() => {
  vi.mocked(useListContext, { partial: true }).mockReturnValue({
    data: [],
    isPending: false,
  });
});
const renderCard = () =>
  render(
    <MemoryRouter>
      <HarvestingSchedulesCardBase>
        <span>Schedules</span>
      </HarvestingSchedulesCardBase>
    </MemoryRouter>,
  );

describe("harvesting schedules overview", () => {
  it("offers creation and management for the current catalogue when no schedule exists", () => {
    renderCard();
    expect(screen.getByText("harvestingSchedules.empty")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "harvestingSchedules.create" }),
    ).toHaveAttribute(
      "href",
      "/CatalogueService/csw-1/show/PeriodicHarvestingJob/create",
    );
    expect(
      screen.getByRole("link", { name: "serviceShow.configure" }),
    ).toHaveAttribute(
      "href",
      "/CatalogueService/csw-1/show/PeriodicHarvestingJob",
    );
  });
  it.each([true, false])(
    "shows enabled=%s schedules without an empty-state action",
    (enabled) => {
      vi.mocked(useListContext, { partial: true }).mockReturnValue({
        data: [{ id: 1, enabled }],
        total: 1,
        isPending: false,
      });
      renderCard();
      expect(
        screen.getByText(
          `harvestingSchedules.${enabled ? "enabled" : "disabled"}`,
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("Schedules")).toBeInTheDocument();
      expect(
        screen.queryByText("harvestingSchedules.create"),
      ).not.toBeInTheDocument();
      expect(
        Boolean(screen.queryByText("harvestingSchedules.disabledMessage")),
      ).toBe(!enabled);
    },
  );
  it("does not claim settings are missing while loading", () => {
    vi.mocked(useListContext, { partial: true }).mockReturnValue({
      data: undefined,
      isPending: true,
    });
    renderCard();
    expect(screen.getByText("Loading")).toBeInTheDocument();
    expect(
      screen.queryByText("harvestingSchedules.create"),
    ).not.toBeInTheDocument();
  });
  it("reports load errors without suggesting creation", () => {
    vi.mocked(useListContext, { partial: true }).mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("Offline"),
    });
    renderCard();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingSchedules.loadError",
    );
    expect(
      screen.queryByText("harvestingSchedules.create"),
    ).not.toBeInTheDocument();
  });
});

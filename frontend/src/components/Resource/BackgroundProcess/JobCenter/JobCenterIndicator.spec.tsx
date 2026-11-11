import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import JobCenterIndicator from "./JobCenterIndicator";

const state = vi.hoisted(() => ({
  open: false,
  setOpen: vi.fn(),
  wide: true,
  countFilters: [] as Record<string, string>[],
}));

vi.mock("./BackgroundJobCenterContext", () => ({
  useBackgroundJobCenter: () => ({
    state: { jobs: {} },
    open: state.open,
    setOpen: state.setOpen,
    clearCompleted: vi.fn(),
  }),
}));

vi.mock("../../../../jsonapi/components/Count", () => ({
  Count: ({ filter }: { filter: Record<string, string> }) => {
    state.countFilters.push(filter);
    return <span>7</span>;
  },
}));

vi.mock("@mui/material", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@mui/material")>()),
  useMediaQuery: () => state.wide,
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

beforeEach(() => {
  state.open = false;
  state.setOpen = vi.fn();
  state.wide = true;
  state.countFilters = [];
  vi.clearAllMocks();
});

describe("JobCenterIndicator", () => {
  it("shows the running, waiting and failed totals of the api on wide screens", () => {
    render(<JobCenterIndicator />);
    expect(
      state.countFilters.filter((filter) => filter.status === "running"),
    ).toHaveLength(1);
    expect(
      state.countFilters.filter((filter) => filter.status === "pending"),
    ).toHaveLength(1);
    expect(
      state.countFilters.filter(
        (filter) => filter.status === "failed,aborted",
      ),
    ).toHaveLength(1);
    expect(screen.getAllByText("7")).toHaveLength(3);
    expect(
      screen.getByRole("button", {
        name: "backgroundActivity.jobCenter.title",
      }),
    ).toBeInTheDocument();
  });

  it("opens the job center on a click", () => {
    render(<JobCenterIndicator />);
    fireEvent.click(
      screen.getByRole("button", {
        name: "backgroundActivity.jobCenter.title",
      }),
    );
    expect(state.setOpen).toHaveBeenCalledWith(true);
  });

  it("falls back to the bare icon on narrow screens", () => {
    state.wide = false;
    render(<JobCenterIndicator />);
    expect(state.countFilters).toHaveLength(0);
    fireEvent.click(
      screen.getByRole("button", {
        name: "backgroundActivity.jobCenter.title",
      }),
    );
    expect(state.setOpen).toHaveBeenCalledWith(true);
  });
});

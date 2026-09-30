import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGetList, useListContext } from "react-admin";
import UpdateJobsCardBase from "./UpdateJobsCardBase";

vi.mock("react-admin", () => ({
  CreateButton: ({ to, label }: { to: string; label: string }) => (
    <a href={to}>{label}</a>
  ),
  Loading: () => <span>Loading</span>,
  useGetList: vi.fn(),
  useListContext: vi.fn(),
  useRecordContext: () => ({ id: "wms-1" }),
  useCreatePath:
    () =>
    ({ resource, id }: { resource: string; id: string }) =>
      `/${resource}/${id}/show`,
  useTranslate: () => (key: string) => key.split(".").pop(),
}));

beforeEach(() => {
  vi.mocked(useListContext, { partial: true }).mockReturnValue({
    data: [],
    isPending: false,
  });
  vi.mocked(useGetList, { partial: true }).mockReturnValue({
    data: [],
    isPending: false,
  });
});

const renderCard = () =>
  render(
    <UpdateJobsCardBase>
      <span>Job list</span>
    </UpdateJobsCardBase>,
  );

describe("update jobs empty state", () => {
  it("offers creation for this service when no setting exists", () => {
    renderCard();
    expect(screen.getByText("noSetting")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "createSetting" })).toHaveAttribute(
      "href",
      "/WebMapService/wms-1/show/WebMapServiceUpdateSetting/create",
    );
    expect(useGetList).toHaveBeenCalledWith(
      "WebMapServiceUpdateSetting",
      expect.objectContaining({ filter: { service: "wms-1" } }),
      expect.anything(),
    );
    expect(
      screen.queryByText("lastUpdateJobsSubheader"),
    ).not.toBeInTheDocument();
  });

  it.each([
    [false, false, "settingsDisabled"],
    [true, false, "waitingForFirstRun"],
    [true, true, "runOverdue"],
    [false, true, "settingsDisabled"],
  ])(
    "distinguishes enabled=%s and overdue=%s",
    (enabled, runOverdue, message) => {
      vi.mocked(useGetList, { partial: true }).mockReturnValue({
        data: [{ id: 1, enabled, runOverdue }],
        isPending: false,
      });
      renderCard();
      expect(screen.getByText(message)).toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      if (enabled && runOverdue)
        expect(screen.getByRole("alert")).toHaveTextContent(message);
    },
  );

  it("does not suggest creating a setting while loading", () => {
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      data: undefined,
      isPending: true,
    });
    renderCard();
    expect(screen.getByText("Loading")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("reports settings errors without claiming settings are missing", () => {
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("Offline"),
    });
    renderCard();
    expect(screen.getByRole("alert")).toHaveTextContent("settingsLoadError");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("preserves review status and the job list when jobs exist", () => {
    vi.mocked(useListContext, { partial: true }).mockReturnValue({
      data: [{ id: 1, statusCode: 2 }],
      isPending: false,
    });
    renderCard();
    expect(screen.getByText("reviewRequired")).toBeInTheDocument();
    expect(screen.getByText("Job list")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("warns about a missed schedule even when older results exist", () => {
    vi.mocked(useListContext, { partial: true }).mockReturnValue({
      data: [{ id: 1, success: true, statusCode: 4 }],
      isPending: false,
    });
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      data: [{ id: 1, enabled: true, runOverdue: true }],
      isPending: false,
    });
    renderCard();
    expect(screen.getByRole("alert")).toHaveTextContent("runOverdue");
    expect(screen.getByText("Job list")).toBeInTheDocument();
    expect(
      screen.queryByText("lastUpdateJobsSubheader"),
    ).not.toBeInTheDocument();
    expect(useGetList).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ enabled: true, refetchInterval: 30_000 }),
    );
  });
});

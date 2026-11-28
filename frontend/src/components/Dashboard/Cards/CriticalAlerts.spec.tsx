import { useGetOne } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SystemStatusProvider } from "../../../context/SystemStatusContext";
import CriticalAlerts from "./CriticalAlerts";

// #1805: the read is gated on the access table of #836, so the specs run as a
// caller which may read the status by default and name the refused one below
const access = vi.hoisted(() => ({ canAccess: true, isPending: false }));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  // the context of the system status reads its one record through this hook,
  // so the answers of the api are the seam the spec measures
  useGetOne: vi.fn(),
  // the provider only asks for the status with a session (#833)
  useAuthState: () => ({ authenticated: true }),
  useCanAccess: () => ({ canAccess: access.canAccess, isPending: access.isPending }),
  useTranslate: () => (key: string) => key,
  useCreatePath:
    () =>
    ({ resource }: { resource: string }) =>
      `/${resource}/list`,
  Link: ({ to, children }: { to: string; children?: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

/** the observation of the four components of the deployment, healthy unless a
 *  test names a state for one of them */
const observation = (states: Record<string, string> = {}) => ({
  id: "current",
  observedAt: new Date().toISOString(),
  stale: false,
  staleAfter: 45,
  components: {
    workers: { status: "healthy", detail: "2 workers responding" },
    beat: { status: "healthy", detail: "Beat scheduler healthcheck passed" },
    redis: { status: "healthy", detail: "Reachable" },
    database: { status: "healthy", detail: "Reachable" },
    ...Object.fromEntries(
      Object.entries(states).map(([name, status]) => [
        name,
        { status, detail: `the answer of ${name}` },
      ]),
    ),
  },
});

const answered = (answer: Record<string, unknown>) =>
  vi
    .mocked(useGetOne)
    .mockReturnValue(answer as unknown as ReturnType<typeof useGetOne>);

/** the card rendered with the real context of the system status, so the states
 *  below are the states the context answers and not a mock of them */
const renderCard = () =>
  render(
    <SystemStatusProvider>
      <CriticalAlerts />
    </SystemStatusProvider>,
  );

beforeEach(() => {
  access.canAccess = true;
  access.isPending = false;
  vi.mocked(useGetOne).mockReset();
  answered({ data: observation(), isPending: false });
});

describe("CriticalAlerts", () => {
  it("answers nothing while the deployment is healthy", () => {
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
    // the card reads nothing of its own: the states are the answer of the
    // request the app bar already owns, so the dashboard never asks twice
    expect(useGetOne).toHaveBeenCalledTimes(1);
  });

  it("answers nothing while the status is still being read", () => {
    answered({ isPending: true });
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
  });

  it("answers nothing to a caller who may not read the status and keeps the dashboard", () => {
    answered({
      isPending: false,
      error: Object.assign(new Error("Forbidden"), {
        response: { status: 403 },
      }),
    });
    const { container } = renderCard();
    // no card and no redirect: the card is an administrator view and the
    // caller stays on the dashboard (#1804 coordinates the access bugs)
    expect(container).toBeEmptyDOMElement();
  });

  it("asks nothing of a caller the access check refuses and keeps the dashboard", () => {
    // #1805: the status endpoint is IsAdminUser, so the deployment answers
    // every persona but an administrator with a 403. The card must not be the
    // reason the app pays for it: the access table refuses the read, and the
    // dashboard renders without the card and without a redirect.
    access.canAccess = false;
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
    expect(vi.mocked(useGetOne).mock.calls[0][2]).toMatchObject({
      enabled: false,
    });
  });

  it("keeps the dashboard while the access check of the read still runs", () => {
    // a check which has not answered is not a refusal either way: no read is
    // fired yet, and no card claims the deployment is healthy
    access.isPending = true;
    answered({ isPending: true });
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
    expect(vi.mocked(useGetOne).mock.calls[0][2]).toMatchObject({
      enabled: false,
    });
  });

  it("answers a component which is down with an error and names it", () => {
    answered({ data: observation({ workers: "down" }), isPending: false });
    renderCard();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("MuiAlert-colorError");
    expect(
      screen.getByText("dashboard.criticalAlerts.down", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("systemStatus.workers")).toBeInTheDocument();
    expect(screen.queryByText("systemStatus.database")).not.toBeInTheDocument();
  });

  it("answers a degraded component with a warning", () => {
    answered({ data: observation({ redis: "degraded" }), isPending: false });
    renderCard();
    expect(screen.getByRole("alert")).toHaveClass("MuiAlert-colorWarning");
    expect(
      screen.getByText("dashboard.criticalAlerts.degraded", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("systemStatus.redis")).toBeInTheDocument();
  });

  it("keeps the severities of the two states apart, the errors first", () => {
    answered({
      data: observation({
        workers: "down",
        beat: "degraded",
        redis: "degraded",
      }),
      isPending: false,
    });
    renderCard();
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(2);
    expect(alerts[0]).toHaveClass("MuiAlert-colorError");
    expect(alerts[1]).toHaveClass("MuiAlert-colorWarning");
    expect(screen.getByText("systemStatus.beat")).toBeInTheDocument();
    expect(screen.getByText("systemStatus.redis")).toBeInTheDocument();
    expect(screen.queryByText("systemStatus.database")).not.toBeInTheDocument();
  });

  it("links the state to the authoritative details screen instead of duplicating it", () => {
    answered({ data: observation({ database: "down" }), isPending: false });
    renderCard();
    expect(
      screen.getByRole("link", { name: "systemStatus.viewDetails" }),
    ).toHaveAttribute("href", "/SystemInfo/list");
    // the answer of a component - its message and heartbeat - belongs to that
    // screen and is not repeated above the inventory
    expect(
      screen.queryByText("the answer of database"),
    ).not.toBeInTheDocument();
  });

  it("warns about an unreadable status instead of a healthy deployment", () => {
    // a refused read of the status - the same answer the context reads as
    // stale - never leaves the last observation of the components standing as
    // the current state of the deployment
    answered({
      isPending: false,
      data: observation({ workers: "down" }),
      error: Object.assign(new Error("Unavailable"), {
        response: { status: 503 },
      }),
    });
    renderCard();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("MuiAlert-colorWarning");
    expect(
      screen.getByText("systemStatus.stale", { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.criticalAlerts.down", { exact: false }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("systemStatus.workers")).not.toBeInTheDocument();
  });

  it("warns when the observation is older than the deployment allows", () => {
    answered({
      isPending: false,
      data: { ...observation({ workers: "down" }), observedAt: "not a moment" },
    });
    renderCard();
    expect(screen.getByRole("alert")).toHaveClass("MuiAlert-colorWarning");
    expect(
      screen.getByText("systemStatus.stale", { exact: false }),
    ).toBeInTheDocument();
  });
});

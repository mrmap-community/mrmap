import { render, screen } from "@testing-library/react";
import { ResourceContext, useGetList } from "ra-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Count } from "./Count";

vi.mock("react-admin", () => ({
  Link: ({ children }: { to: unknown; children?: React.ReactNode }) => (
    <a>{children}</a>
  ),
}));

vi.mock("ra-core", async () => {
  const actual = await vi.importActual<typeof import("ra-core")>("ra-core");
  return {
    ...actual,
    useCreatePath: () => () => "/ServiceAlert/list",
    useGetList: vi.fn(),
    // the spinner of a long read is not what the four answers are about
    useTimeout: () => false,
  };
});

const answered = (answer: Record<string, unknown>) =>
  vi
    .mocked(useGetList)
    .mockReturnValue(answer as unknown as ReturnType<typeof useGetList>);

const renderCount = (props?: { filter?: Record<string, unknown> }) =>
  render(
    <ResourceContext value="ServiceAlert">
      <Count link variant="h5" {...props} />
    </ResourceContext>,
  );

beforeEach(() => {
  vi.mocked(useGetList).mockReset();
});

describe("Count", () => {
  it("answers the total of the api, which is more than the records of a page", () => {
    answered({ total: 42, isPending: false, error: undefined });
    renderCount({ filter: { category: "update_review_required" } });
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(useGetList).toHaveBeenCalledWith(
      "ServiceAlert",
      expect.objectContaining({
        filter: { category: "update_review_required" },
        pagination: { perPage: 1, page: 1 },
      }),
      expect.anything(),
    );
  });

  it("answers a real zero and never hides it behind the answer of a failure", () => {
    answered({ total: 0, isPending: false, error: undefined });
    renderCount();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("answers nothing but the wait while the api has not answered", () => {
    answered({ total: 0, isPending: true, error: undefined });
    renderCount();
    // while the read is out, zero would read as "nothing waits"
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("marks a read the api refuses, instead of counting it as none", () => {
    answered({ total: 0, isPending: false, error: { status: 500 } });
    renderCount();
    expect(screen.getByTitle("error")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("marks a read the caller may not perform apart from a failing one", () => {
    for (const status of [401, 403]) {
      answered({ total: 0, isPending: false, error: { status } });
      const { unmount } = renderCount();
      // the queue still answers its icon and its link, but it says that this
      // caller may not read it instead of reporting a failure of the api
      expect(screen.getByTitle("unauthorized")).toBeInTheDocument();
      expect(screen.queryByTitle("error")).not.toBeInTheDocument();
      expect(screen.queryByText("0")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("reads the status of a nested http response as well", () => {
    answered({
      total: 0,
      isPending: false,
      error: { response: { status: 403 } },
    });
    renderCount();
    expect(screen.getByTitle("unauthorized")).toBeInTheDocument();
  });
});

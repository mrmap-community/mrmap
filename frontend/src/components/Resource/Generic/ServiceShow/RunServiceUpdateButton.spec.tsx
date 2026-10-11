import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGetIdentity, useGetList, useResourceDefinition } from "react-admin";
import RunServiceUpdateButton from "./RunServiceUpdateButton";

const { create, notify, refresh, mutation } = vi.hoisted(() => ({
  create: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  mutation: { isPending: false },
}));
vi.mock("react-admin", () => ({
  Button: ({
    label,
    onClick,
    disabled,
  }: {
    label: string;
    onClick: () => void;
    disabled: boolean;
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {label}
    </button>
  ),
  ShowButton: ({
    record,
    resource,
    label,
  }: {
    record: { id: number };
    resource: string;
    label: string;
  }) => <a href={`/${resource}/${record.id}/show`}>{label}</a>,
  useCreate: () => [create, mutation],
  useGetIdentity: vi.fn(),
  useGetList: vi.fn(),
  useResourceDefinition: vi.fn(),
  useNotify: () => notify,
  useRefresh: () => refresh,
  useTranslate: () => (key: string) => key,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mutation.isPending = false;
  vi.mocked(useGetIdentity, { partial: true }).mockReturnValue({
    data: { id: 1 },
  });
  vi.mocked(useGetList, { partial: true }).mockReturnValue({
    data: [],
    isPending: false,
  });
  vi.mocked(useResourceDefinition, { partial: true }).mockReturnValue({
    hasCreate: true,
  });
});

const renderButton = (resource = "WebMapServiceUpdateJob") =>
  render(<RunServiceUpdateButton resource={resource} serviceId="service-1" />);

describe("manual service updates", () => {
  it.each([
    "WebMapServiceUpdateJob",
    "WebFeatureServiceUpdateJob",
    "CatalogueServiceUpdateJob",
  ])("creates %s using only the service relationship", (resource) => {
    renderButton(resource);
    fireEvent.click(screen.getByRole("button"));
    expect(create).toHaveBeenCalledWith(
      resource,
      { data: { service: { id: "service-1" } } },
      expect.anything(),
    );
    create.mock.calls[0][2].onSuccess();
    expect(notify).toHaveBeenCalledWith("manualUpdate.queued", {
      type: "success",
    });
    expect(refresh).toHaveBeenCalled();
    expect(useGetList).toHaveBeenCalledWith(
      resource,
      expect.objectContaining({
        filter: { service: "service-1", "doneAt.isnull": true },
      }),
      expect.anything(),
    );
  });

  it("links to an unfinished job instead of creating another", () => {
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      data: [{ id: 42, statusCode: 2 }],
      isPending: false,
    });
    renderButton();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/WebMapServiceUpdateJob/42/show",
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("disables submission while pending", () => {
    mutation.isPending = true;
    renderButton();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("reports failures and refreshes to discover concurrent jobs", () => {
    renderButton();
    fireEvent.click(screen.getByRole("button"));
    create.mock.calls[0][2].onError();
    expect(notify).toHaveBeenCalledWith("manualUpdate.failed", {
      type: "error",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("blocks creation when the unfinished-job query fails", () => {
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      error: new Error("offline"),
      isPending: false,
    });
    renderButton();
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "manualUpdate.loadError",
    );
  });

  it("hides creation from anonymous users", () => {
    vi.mocked(useGetIdentity, { partial: true }).mockReturnValue({
      data: { id: 0 },
    });
    renderButton();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("honors schema-derived create support", () => {
    vi.mocked(useResourceDefinition, { partial: true }).mockReturnValue({
      hasCreate: false,
    });
    renderButton();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

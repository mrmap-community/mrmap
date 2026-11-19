import {
  AdminContext,
  RecordContextProvider,
  testDataProvider,
  type RaRecord,
} from "react-admin";

import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi, type Mock } from "vitest";

import de from "../../../../i18n/de";
import en from "../../../../i18n/en";
import { getPermissionSnapshot } from "../../../../providers/authProvider";
import ServiceOwnerField from "./ServiceOwnerField";

// the row asks the cached who-am-i snapshot only whether this caller has a
// session at all: without one no organization is readable
vi.mock("../../../../providers/authProvider", () => ({
  getPermissionSnapshot: vi.fn(),
}));

const SIGNED_IN = Promise.resolve({
  roles: [],
  administeredOrganizationIds: [],
  isSuperuser: false,
});

const renderOwner = async ({
  record,
  getList,
  hintWhenAbsent = false,
  locale = "en",
}: {
  record: RaRecord;
  getList: Mock;
  hintWhenAbsent?: boolean;
  locale?: "en" | "de";
}) =>
  render(
    <AdminContext
      i18nProvider={polyglotI18nProvider(
        () => (locale === "de" ? de : en),
        locale,
      )}
      dataProvider={testDataProvider({ getList })}
      queryClient={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <RecordContextProvider value={record}>
        <ServiceOwnerField hintWhenAbsent={hintWhenAbsent} />
      </RecordContextProvider>
    </AdminContext>,
  );

describe("the owning organization of a service (#733)", () => {
  it("names the organization the record points at", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockResolvedValue({
      data: [{ id: "901", stringRepresentation: "City of Springfields" }],
      total: 1,
    });

    await renderOwner({ record: { id: "wms", owner: { id: 901 } }, getList });

    expect(await screen.findByText("Owning organization")).toBeInTheDocument();
    expect(screen.getByText("City of Springfields")).toBeInTheDocument();
    // the page and order the organization screens already ask for: the name of
    // one organization is read from the readable ones, not by refusing a record
    expect(getList).toHaveBeenCalledWith(
      "Organization",
      expect.objectContaining({
        pagination: { page: 1, perPage: 100 },
        sort: { field: "stringRepresentation", order: "ASC" },
      }),
    );
  });

  it("translates the row into German", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockResolvedValue({
      data: [{ id: "901", name: "Stadt Springfeld" }],
      total: 1,
    });

    await renderOwner({
      record: { id: "wms", owner: { id: "901" } },
      getList,
      locale: "de",
    });

    expect(
      await screen.findByText("Eigentümerorganisation"),
    ).toBeInTheDocument();
    expect(screen.getByText("Stadt Springfeld")).toBeInTheDocument();
  });

  it.each([
    { name: "names no owner", record: { id: "wms" } },
    { name: "answers an empty owner", record: { id: "wms", owner: null } },
  ])("asks for nothing when a service $name", async ({ record }) => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockResolvedValue({ data: [], total: 0 });

    await renderOwner({ record: record as RaRecord, getList });

    expect(getList).not.toHaveBeenCalled();
    expect(screen.queryByText("Owning organization")).not.toBeInTheDocument();
  });

  it("tells a shown service's ownerless state apart from an unanswered question", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockResolvedValue({ data: [], total: 0 });

    await renderOwner({
      record: { id: "wms" },
      getList,
      hintWhenAbsent: true,
    });

    expect(screen.getByText("Owning organization")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No owning organization is stored. This service was registered before ownership was stored.",
      ),
    ).toBeInTheDocument();
    expect(getList).not.toHaveBeenCalled();
  });

  it("asks nothing for a caller without a session, which may not read organizations", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(undefined);
    const getList = vi.fn().mockResolvedValue({ data: [], total: 0 });

    await renderOwner({
      record: { id: "wms", owner: { id: "901" } },
      getList,
      hintWhenAbsent: true,
    });

    expect(getList).not.toHaveBeenCalled();
    expect(screen.queryByText("Owning organization")).not.toBeInTheDocument();
  });

  it("names an owner which cannot be read instead of pretending it is absent", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockRejectedValue(new Error("forbidden"));

    await renderOwner({
      record: { id: "wms", owner: { id: "901" } },
      getList,
      hintWhenAbsent: true,
    });

    expect(await screen.findByText("not readable")).toBeInTheDocument();
    expect(
      screen.queryByText(/before ownership was stored/),
    ).not.toBeInTheDocument();
  });

  it("says the name is not readable when the owner is not among the readable organizations", async () => {
    vi.mocked(getPermissionSnapshot).mockReturnValue(SIGNED_IN);
    const getList = vi.fn().mockResolvedValue({
      data: [{ id: "7", stringRepresentation: "My Own Organization" }],
      total: 1,
    });

    await renderOwner({
      record: { id: "wms", owner: { id: "901" } },
      getList,
    });

    expect(await screen.findByText("not readable")).toBeInTheDocument();
    expect(
      screen.queryByText("My Own Organization"),
    ).not.toBeInTheDocument();
  });
});

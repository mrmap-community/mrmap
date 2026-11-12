import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RecordDocuments from "./RecordDocuments";

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
}));
vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
}));

describe("stored documents of a record", () => {
  it("answers nothing while the record is still loading", () => {
    state.record = undefined;
    const { container } = render(<RecordDocuments />);
    expect(container).toBeEmptyDOMElement();
  });
  it("links the xml document the api answers as its stored file", () => {
    state.record = { id: 1, xmlBackupFile: "/media/xml_backup/doc.xml" };
    render(<RecordDocuments />);
    expect(screen.getByText("recordShow.documents")).toBeInTheDocument();
    const link = screen.getByRole("link", {
      name: "recordShow.storedXml",
    });
    expect(link).toHaveAttribute("href", "/media/xml_backup/doc.xml");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("says honestly when no xml document is stored", () => {
    state.record = { id: 1, xmlBackupFile: null };
    render(<RecordDocuments />);
    expect(
      screen.getByRole("alert").textContent,
    ).toContain("recordShow.noStoredXml");
    expect(
      screen.queryByRole("link", { name: "recordShow.storedXml" }),
    ).not.toBeInTheDocument();
  });
});

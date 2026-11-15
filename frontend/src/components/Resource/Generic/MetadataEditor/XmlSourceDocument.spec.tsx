import { ReactNode } from "react";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import XmlSourceDocument from "./XmlSourceDocument";

// monaco is loaded from a cdn, the editor is reduced to what the screen uses
const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  mutate: vi.fn(),
}));

vi.mock("@monaco-editor/react", () => ({
  Editor: ({
    value,
    onChange,
  }: {
    value: string;
    onChange?: (value?: string) => void;
  }) => (
    <textarea
      data-testid="editor"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
    />
  ),
}));

vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useResourceContext: () => "DatasetMetadataRecord",
  useTranslate: () => (key: string) => key.split(".").pop(),
  useNotify: () => vi.fn(),
  useUpdate: () => [state.mutate, { isPending: false }],
}));

vi.mock("../../../MUI/SimpleCard", () => ({
  default: ({ title, children }: { title?: string; children: ReactNode }) => (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  ),
}));

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  mutate: vi.fn(),
}));

const stored = "<xml>stored document</xml>";

const serveDocument = () => {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    text: async () => stored,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

const renderScreen = (record: Record<string, unknown>) => {
  state.record = record;
  const result = render(<XmlSourceDocument />);
  state.mutate.mockReset();
  return result;
};

beforeEach(() => {
  vi.unstubAllGlobals();
  state.mutate.mockReset();
});

describe("the xml source screen of a record", () => {
  it("answers nothing while the record is still loading", () => {
    state.record = undefined;
    const { container } = render(<XmlSourceDocument />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says honestly when no document is stored", () => {
    renderScreen({ id: 1, xmlBackupFile: null, canEdit: true });
    expect(screen.getByRole("alert").textContent).toContain("noStoredXml");
    expect(screen.queryByTestId("editor")).not.toBeInTheDocument();
  });

  it("loads the stored bytes — the same the download offers", async () => {
    const fetchMock = serveDocument();
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: true,
    });
    const editor = await screen.findByTestId("editor");
    expect(editor).toHaveValue(stored);
    expect(fetchMock).toHaveBeenCalledWith("/media/xml_backup/doc.xml");
  });

  it("reports a document which cannot be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 404, text: async () => "" })),
    );
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: true,
    });
    expect(await screen.findByText("sourceLoadFailed")).toBeInTheDocument();
    expect(screen.queryByTestId("editor")).not.toBeInTheDocument();
  });

  it("saves the edited text as a write of the source attribute alone", async () => {
    serveDocument();
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: true,
    });
    const editor = await screen.findByTestId("editor");
    const save = screen.getByRole("button", { name: "sourceSave" });
    // nothing edited yet — the screen offers nothing to save
    expect(save).toBeDisabled();

    fireEvent.change(editor, { target: { value: "<xml>edited</xml>" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(state.mutate).toHaveBeenCalledWith(
      {
        resource: "DatasetMetadataRecord",
        id: 1,
        data: { xmlBackupFile: "<xml>edited</xml>" },
        previousData: state.record,
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("discards the edits back to the served document", async () => {
    serveDocument();
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: true,
    });
    const editor = await screen.findByTestId("editor");
    fireEvent.change(editor, { target: { value: "<xml>weg</xml>" } });
    fireEvent.click(screen.getByRole("button", { name: "sourceDiscard" }));
    expect(editor).toHaveValue(stored);
    expect(state.mutate).not.toHaveBeenCalled();
  });

  it("lists the server's refusal and keeps the editor open", async () => {
    serveDocument();
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: true,
    });
    const editor = await screen.findByTestId("editor");
    fireEvent.change(editor, { target: { value: "<xml><oops" } });
    fireEvent.click(screen.getByRole("button", { name: "sourceSave" }));
    const options = state.mutate.mock.calls[0][1] as {
      onError: (error: unknown) => void;
    };
    options.onError({
      body: {
        errors: {
          xmlBackupFile:
            "The source document is not well-formed XML (line 1, column 12).",
        },
      },
    });

    await waitFor(() =>
      expect(screen.getByTestId("source-errors").textContent).toContain(
        "not well-formed XML",
      ),
    );
    // the editor keeps the curator's text — nothing was lost
    expect(editor).toHaveValue("<xml><oops");
  });

  it("gates editing on the record's canEdit", async () => {
    serveDocument();
    renderScreen({
      id: 1,
      xmlBackupFile: "/media/xml_backup/doc.xml",
      canEdit: false,
    });
    await screen.findByTestId("editor");
    expect(screen.getByRole("button", { name: "sourceSave" })).toBeDisabled();
    expect(screen.getByRole("alert").textContent).toContain("sourceReadOnly");
  });
});

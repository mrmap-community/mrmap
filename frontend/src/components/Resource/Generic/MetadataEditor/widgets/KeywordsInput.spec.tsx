import type { ReactNode } from "react";
import { FormProvider, useForm } from "react-hook-form";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import KeywordsInput from "./KeywordsInput";

vi.mock("react-admin", () => ({
  ArrayInput: ({
    source,
    children,
  }: {
    source?: string;
    children?: ReactNode;
  }) => <div data-testid={`array-${source}`}>{children}</div>,
  SimpleFormIterator: ({ children }: { children?: ReactNode }) => (
    <div>{children}</div>
  ),
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
// the row picker and its create dialog carry the whole schema layer; their
// own specs cover them — here it is enough to see they are placed per row
vi.mock("../../../../../jsonapi/components/SchemaAutocompleteInput", () => ({
  default: () => <div>keyword-picker</div>,
}));
vi.mock("../../../../Dialog/CreateSuggestionDialog", () => ({
  default: () => null,
}));

// the form value of the keyword field, as the editor's form holds it: rows
// arrive as { id } references or as completed include records
const renderWidget = (keywords: unknown) => {
  const Wrapper = () => {
    const methods = useForm({ defaultValues: { keywords } });
    return (
      <FormProvider {...methods}>
        <KeywordsInput
          source="keywords"
          reference="Keyword"
          label="Keywords"
        />
      </FormProvider>
    );
  };
  render(<Wrapper />);
};

describe("KeywordsInput", () => {
  it("places the row picker inside the array input", () => {
    renderWidget([{ id: "k1", stringRepresentation: "alpha" }]);
    expect(screen.getByTestId("array-keywords")).toBeInTheDocument();
    expect(screen.getByText("keyword-picker")).toBeInTheDocument();
  });

  it("previews the gco:CharacterString form the write emits", () => {
    renderWidget([{ id: "k1", stringRepresentation: "alpha" }, { id: "k2" }]);
    const preview = screen.getByText(/CharacterString/);
    expect(preview.textContent).toContain(
      "<gco:CharacterString>alpha</gco:CharacterString>",
    );
    // an unresolved reference is shown by id rather than guessed away
    expect(preview.textContent).toContain(
      "<gco:CharacterString>#k2</gco:CharacterString>",
    );
    expect(screen.getByText("preview")).toBeInTheDocument();
  });

  it("shows no preview while the set is empty", () => {
    renderWidget([]);
    expect(screen.queryByText("preview")).not.toBeInTheDocument();
  });
});

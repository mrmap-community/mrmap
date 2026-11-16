import type { ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ContactChooser from "./ContactChooser";

// what the chooser hands the schema input; the spec reads the props back to
// assert the reuse count is asked for and shown
interface Captured {
  source?: string;
  params?: { meta?: { jsonApiParams?: Record<string, string> } };
  renderOption?: (
    props: { key?: string | number },
    option: Record<string, unknown>,
    state: { selected: boolean },
  ) => ReactNode;
}
const passed = vi.hoisted(() => ({ props: undefined as unknown }));

vi.mock("react-admin", () => ({
  useTranslate:
    () =>
    (key: string, options?: { smart_count?: number }) =>
      options?.smart_count !== undefined
        ? `${key.split(".").pop()}:${options.smart_count}`
        : key.split(".").pop(),
}));
vi.mock("../../../../../jsonapi/hooks/useSchemaRecordRepresentation", () => ({
  default: () => (record: { stringRepresentation?: string; id?: string }) =>
    record?.stringRepresentation ?? `#${record?.id}`,
}));
vi.mock("../../../../../jsonapi/components/SchemaAutocompleteInput", () => ({
  default: (props: unknown) => {
    passed.props = props;
    return <div>chooser</div>;
  },
}));

const capturedProps = (): Captured => passed.props as Captured;

describe("ContactChooser", () => {
  it("asks the contact list endpoint for the reuse count", () => {
    render(<ContactChooser source="metadataContact" reference="MetadataContact" />);
    expect(screen.getByText("chooser")).toBeInTheDocument();
    expect(
      capturedProps().params?.meta?.jsonApiParams?.[
        "fields[MetadataContact]"
      ],
    ).toBe("id,string_representation,usage_count");
  });

  it("shows the reuse count on options that carry one", () => {
    render(<ContactChooser source="metadataContact" reference="MetadataContact" />);
    const { renderOption } = capturedProps();
    expect(renderOption).toBeDefined();
    render(
      <ul>
        {renderOption?.(
          { key: "c1" },
          { id: "c1", stringRepresentation: "Rep A", usageCount: 3 },
          { selected: false },
        )}
        {renderOption?.(
          { key: "c2" },
          { id: "c2", stringRepresentation: "Rep B" },
          { selected: false },
        )}
      </ul>,
    );
    expect(screen.getByText("Rep A")).toBeInTheDocument();
    expect(screen.getByText("reused:3")).toBeInTheDocument();
    // an option from the include, which carries no count, shows no chip:
    // only the option with a count contributes one
    expect(screen.getByText("Rep B")).toBeInTheDocument();
    expect(screen.getAllByText(/^reused:/)).toHaveLength(1);
  });
});

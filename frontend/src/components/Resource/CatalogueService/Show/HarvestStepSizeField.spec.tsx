import type { ElementType, ReactNode } from "react";
import { AdminContext, NumberInput, SimpleForm } from "react-admin";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SchemaFormFields from "../../../../jsonapi/components/SchemaFormFields";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import HarvestStepSizeField from "./HarvestStepSizeField";

vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  useResourceContext: vi.fn(() => "CatalogueService"),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: vi.fn(() => []),
}));
vi.mock("./HarvestThroughputHint", () => ({
  default: ({
    serviceId,
    currentSize,
  }: {
    serviceId: string;
    currentSize?: number;
  }) => (
    <span data-testid="hint">
      {`${String(serviceId)} ${String(currentSize)}`}
    </span>
  ),
}));

/**
 * the input the schema answers for the size of a harvest, marked to be readable
 *
 * It renders what it is handed as `helperText`, because that is what an input
 * answers below itself and where a screen adds the measurement to.
 */
const SizeInput = (props: Record<string, unknown>) => (
  <span data-testid="input">
    {`${String(props.label)} ${String(props.max)}`}
    {props.helperText as ReactNode}
  </span>
);

const SIZE = {
  component: SizeInput as ElementType,
  props: {
    source: "maxStepSize",
    label: "Max step size",
    max: 32767,
    min: 1,
    helperText: "the step size the harvesting runs of this catalogue start with",
  },
};

const fields = (definitions: unknown[]) =>
  vi.mocked(useFieldsForOperation).mockReturnValue(
    definitions as ReturnType<typeof useFieldsForOperation>,
  );

beforeEach(() => {
  fields([]);
});

describe("the size a harvest starts with, with what the harvests measured", () => {
  it("binds the schema input to the form's step size", () => {
    fields([{ ...SIZE, component: NumberInput }]);
    const record = { id: "csw-1", maxStepSize: 50 };
    render(
      <AdminContext>
        <SimpleForm record={record} toolbar={false}>
          <SchemaFormFields
            operationId="partial_update_CatalogueService"
            overrides={[
              { component: HarvestStepSizeField, props: { source: "maxStepSize" } },
            ]}
            record={record}
          />
        </SimpleForm>
      </AdminContext>,
    );
    const input = screen.getByRole("spinbutton", { name: "Max step size" });
    expect(input).toHaveAttribute("name", "maxStepSize");
    expect(input).toHaveValue(50);
    expect(input).toHaveAttribute("min", "1");
    expect(input).toHaveAttribute("max", "32767");
    expect(screen.getByText(SIZE.props.helperText)).toBeInTheDocument();
  });

  it("asks the fields of the resource which is edited", () => {
    fields([SIZE]);
    render(<HarvestStepSizeField source="maxStepSize" />);
    expect(useFieldsForOperation).toHaveBeenCalledWith({
      operationId: "partial_update_CatalogueService",
    });
  });

  it("renders the input the schema answers, with its label and its limits", () => {
    fields([SIZE]);
    render(
      <HarvestStepSizeField
        source="maxStepSize"
        label="Max step size"
        max={32767}
        min={1}
        helperText="the step size the harvesting runs of this catalogue start with"
        record={{ id: "csw-1", maxStepSize: 50 }}
      />,
    );
    expect(screen.getByTestId("input")).toHaveTextContent("Max step size 32767");
  });

  it("adds what the harvests of the catalogue measured to the input", () => {
    fields([SIZE]);
    render(
      <HarvestStepSizeField
        source="maxStepSize"
        label="Max step size"
        record={{ id: "csw-1", maxStepSize: 50 }}
      />,
    );
    const input = screen.getByTestId("input");
    expect(within(input).getByTestId("hint")).toHaveTextContent("csw-1 50");
  });

  it("answers the measurement where the input describes itself", () => {
    fields([{ ...SIZE, component: NumberInput }]);
    const record = { id: "csw-1", maxStepSize: 50 };
    render(
      <AdminContext>
        <SimpleForm record={record} toolbar={false}>
          <HarvestStepSizeField {...SIZE.props} record={record} />
        </SimpleForm>
      </AdminContext>,
    );
    const measurement = screen.getByTestId("hint");
    // the description of the size and its measurement are the one helper text of
    // the input - the measurement reads as what the input says about itself
    expect(measurement.parentElement).toBe(
      screen.getByText(SIZE.props.helperText),
    );
    expect(screen.getByRole("spinbutton", { name: "Max step size" })).toHaveAttribute(
      "aria-describedby",
      measurement.parentElement?.id,
    );
  });

  it("names no measurement of a catalogue which is not there yet", () => {
    fields([SIZE]);
    render(<HarvestStepSizeField source="maxStepSize" label="Max step size" />);
    const input = screen.getByTestId("input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveTextContent(SIZE.props.helperText);
    expect(screen.queryByTestId("hint")).not.toBeInTheDocument();
  });

  it("renders nothing where no size is set", () => {
    fields([]);
    const { container } = render(
      <HarvestStepSizeField source="maxStepSize" record={{ id: "csw-1" }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

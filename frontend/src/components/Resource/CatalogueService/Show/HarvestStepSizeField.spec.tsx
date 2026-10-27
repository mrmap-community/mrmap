import type { ElementType } from "react";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import HarvestStepSizeField from "./HarvestStepSizeField";

vi.mock("react-admin", () => ({
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

/** the input the schema answers for the size of a harvest, marked to be readable */
const SizeInput = (props: Record<string, unknown>) => (
  <span data-testid="input">{`${String(props.label)} ${String(props.max)}`}</span>
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
    expect(screen.getByTestId("hint")).toHaveTextContent("csw-1 50");
  });

  it("names no measurement of a catalogue which is not there yet", () => {
    fields([SIZE]);
    render(<HarvestStepSizeField source="maxStepSize" label="Max step size" />);
    expect(screen.getByTestId("input")).toBeInTheDocument();
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

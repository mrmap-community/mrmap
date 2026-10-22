import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import ListServiceAlert from "./ListServiceAlert";

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../../jsonapi/hooks/useFilterInputForOperation", () => ({
  useFilterInputForOperation: () => [],
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  DateField: () => null,
  FunctionField: () => null,
  TextField: () => null,
}));
describe("ListServiceAlert", () => {
  it("uses schema filters, realtime and polling, and links to the resolving workflow", () => {
    render(<ListServiceAlert />);
    const props = vi.mocked(ListGuesser).mock.calls[0][0];
    expect(props.realtime).toBe(true);
    expect(props.refetchInterval).toBe(20000);
    expect(props.sort).toEqual({ field: "severity,-occurredAt", order: "ASC" });
    const rowClick = props.dataGridProps?.rowClick;
    expect(typeof rowClick).toBe("function");
    if (typeof rowClick === "function") {
      expect(
        rowClick("a", "ServiceAlert", {
          id: "a",
          targetPath: "/WebMapServiceUpdateJob/2/show",
        }),
      ).toBe("/WebMapServiceUpdateJob/2/show");
    }
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DurationField from "./DurationField";

const state = vi.hoisted(() => ({
  value: undefined as unknown,
}));

vi.mock("react-admin", () => ({
  useFieldValue: () => state.value,
}));

describe("DurationField", () => {
  it("renders the clock form of seconds below an hour", () => {
    state.value = 184.4;
    render(<DurationField source="duration" />);
    expect(screen.getByText("00:03:04")).toBeInTheDocument();
  });

  it("renders hours without days", () => {
    state.value = 2 * 3600 + 3 * 60 + 4;
    render(<DurationField source="duration" />);
    expect(screen.getByText("02:03:04")).toBeInTheDocument();
  });

  it("renders days beside the clock of the rest", () => {
    state.value = 86400 + 2 * 3600 + 3 * 60 + 4;
    render(<DurationField source="duration" />);
    expect(screen.getByText("1 d 02:03:04")).toBeInTheDocument();
  });

  it("renders the zero of a process which decided in the same second", () => {
    state.value = 0;
    render(<DurationField source="duration" />);
    expect(screen.getByText("00:00:00")).toBeInTheDocument();
  });

  it("renders nothing while the process did not decide", () => {
    state.value = null;
    const { container } = render(<DurationField source="duration" />);
    expect(container).toBeEmptyDOMElement();
  });
});

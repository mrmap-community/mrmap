import { fireEvent, render, screen } from "@testing-library/react";
import { useRecordContext } from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ServicePreviewImage from "./ServicePreviewImage";

vi.mock("react-admin", () => ({
  useRecordContext: vi.fn(),
  useTranslate: () => (key: string, options?: { title?: string }) =>
    key === "serviceShow.preview" ? `Preview of ${options?.title}` : key,
}));

const record = {
  id: "wms-1",
  title: "Service",
  previewUrl: "https://example.com/wms?REQUEST=GetMap&LAYERS=roads,buildings",
};

beforeEach(() => {
  vi.mocked(useRecordContext).mockReturnValue(record);
});

describe("service preview image", () => {
  it("loads the backend URL immediately and replaces the loading placeholder on success", () => {
    render(<ServicePreviewImage />);
    const image = screen.getByAltText("Preview of Service");
    expect(image).toHaveAttribute("src", record.previewUrl);
    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();

    fireEvent.load(image);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(image).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([undefined, null, "", "   "])(
    "shows an unavailable placeholder for a missing URL (%s)",
    (previewUrl) => {
      vi.mocked(useRecordContext).mockReturnValue({ ...record, previewUrl });
      render(<ServicePreviewImage />);

      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(
        "serviceShow.previewUnavailable",
      );
    },
  );

  it("replaces a failed image with the unavailable placeholder", () => {
    render(<ServicePreviewImage />);
    fireEvent.error(screen.getByAltText("Preview of Service"));

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "serviceShow.previewUnavailable",
    );
  });

  it.each([
    { ...record, id: "wms-2" },
    { ...record, previewUrl: "https://example.com/updated-preview.png" },
  ])("loads again after the service or URL changes", (nextRecord) => {
    const view = render(<ServicePreviewImage />);
    fireEvent.error(screen.getByAltText("Preview of Service"));

    vi.mocked(useRecordContext).mockReturnValue(nextRecord);
    view.rerender(<ServicePreviewImage />);

    expect(screen.getByAltText("Preview of Service")).toHaveAttribute(
      "src",
      nextRecord.previewUrl,
    );
    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();
    fireEvent.load(screen.getByAltText("Preview of Service"));
    expect(screen.getByRole("img")).toBeVisible();
  });

  it("waits for a service record", () => {
    vi.mocked(useRecordContext).mockReturnValue(undefined);
    const { container } = render(<ServicePreviewImage />);

    expect(container).toBeEmptyDOMElement();
  });
});

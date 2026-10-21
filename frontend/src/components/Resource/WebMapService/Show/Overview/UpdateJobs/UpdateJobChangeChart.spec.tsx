import { BarChart } from "@mui/x-charts/BarChart";
import { fireEvent, render, screen } from "@testing-library/react";
import { useGetList, useRecordContext, useTranslate } from "ra-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18nProvider from "../../../../../../providers/i18nProvider";
import { LayerChangesChart } from "./UpdateJobChangeChart";

import "@testing-library/jest-dom/vitest";

vi.mock("ra-core", () => ({
  useGetList: vi.fn(),
  useRecordContext: vi.fn(),
  useTranslate: vi.fn(),
}));

vi.mock("@mui/x-charts/BarChart", () => ({
  BarChart: vi.fn(({ yAxis }: { yAxis: { label: string }[] }) => (
    <div role="img" aria-label={yAxis[0].label} />
  )),
}));

const statisticalChanges = [
  { id: "2026-10-12", new: 2, updated: 3, deleted: 1 },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useRecordContext).mockReturnValue({ id: "service-1" });
  vi.mocked(useGetList, { partial: true }).mockReturnValue({
    data: statisticalChanges,
  });
});

describe.each([
  {
    locale: "en",
    wfsTitle: "Feature type changes over time",
    wfsAxis: "Feature types",
    wmsTitle: "Layer changes over time",
    wmsAxis: "Layers",
  },
  {
    locale: "de",
    wfsTitle: "Änderungen an Feature-Typen im Zeitverlauf",
    wfsAxis: "Feature-Typen",
    wmsTitle: "Layer-Änderungen im Zeitverlauf",
    wmsAxis: "Layer",
  },
])("service change chart in $locale", ({ locale, ...labels }) => {
  beforeEach(async () => {
    await i18nProvider.changeLocale(locale);
    vi.mocked(useTranslate).mockReturnValue(i18nProvider.translate);
  });

  it("describes feature type changes for WFS", () => {
    render(<LayerChangesChart resource="WebFeatureServiceUpdateJob" />);

    fireEvent.click(screen.getByText(labels.wfsTitle));

    expect(
      screen.getByRole("img", { name: labels.wfsAxis }),
    ).toBeInTheDocument();
    expect(screen.queryByText(labels.wmsTitle)).not.toBeInTheDocument();
    expect(useGetList).toHaveBeenCalledWith(
      "StatisticalFeatureTypePerService",
      expect.objectContaining({ filter: { service: "service-1" } }),
    );
    expect(vi.mocked(BarChart).mock.calls.at(-1)?.[0].dataset).toEqual(
      statisticalChanges,
    );
  });

  it("preserves layer terminology for WMS", () => {
    render(<LayerChangesChart resource="WebMapServiceUpdateJob" />);

    fireEvent.click(screen.getByText(labels.wmsTitle));

    expect(
      screen.getByRole("img", { name: labels.wmsAxis }),
    ).toBeInTheDocument();
    expect(screen.queryByText(labels.wfsTitle)).not.toBeInTheDocument();
    expect(useGetList).toHaveBeenCalledWith(
      "StatisticalLayerPerService",
      expect.objectContaining({ filter: { service: "service-1" } }),
    );
    expect(vi.mocked(BarChart).mock.calls.at(-1)?.[0].dataset).toEqual(
      statisticalChanges,
    );
  });
});

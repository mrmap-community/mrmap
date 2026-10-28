import type { RaRecord } from "react-admin";
import { AdminContext, ResourceContextProvider, useRecordContext, useResourceContext } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectedRecordContextProvider } from "../../../../jsonapi/components/SelectedRecordContext";
import SelectedElementPreviewCard from "./SelectedElementPreviewCard";

vi.mock("./ElementLivePreview", () => ({
  // the preview reads the element it shows from the record context, which is what the card under
  // test has to hand it
  default: () => {
    const record = useRecordContext<RaRecord>();
    const resource = useResourceContext();
    return <span>live preview of {String(resource)}:{String(record?.id)}</span>;
  },
}));

const renderCard = (selectedRecord?: RaRecord) =>
  render(
    <AdminContext>
      <ResourceContextProvider value="Layer">
        <SelectedRecordContextProvider record={selectedRecord}>
          <SelectedElementPreviewCard />
        </SelectedRecordContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );

describe("the preview aside of a screen of elements", () => {
  it("previews the element the screen selected", () => {
    renderCard({ id: "6b1" });

    expect(screen.getByText("live preview of Layer:6b1")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.preview")).toBeInTheDocument();
  });

  it("names the selection it waits for while nothing is selected", () => {
    renderCard();

    expect(screen.getByText("layerInspection.select")).toBeInTheDocument();
    expect(screen.queryByText(/live preview of/)).toBeNull();
  });
});

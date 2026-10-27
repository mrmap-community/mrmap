import { render, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import CatalogueServiceClient from "./CatalogueServiceClient";

// The viewer renders whatever the request answers; its parsing is not the
// contract asserted here, so it is replaced by its output element.
vi.mock("react-xml-viewer", () => ({
  default: ({ xml }: { xml: string }) => <pre>{xml}</pre>,
}));

describe("CatalogueServiceClient", () => {
  test("queries the catalogue over https and names the ISO 19139 schema as parameter value", async () => {
    const fetch = vi.fn().mockResolvedValue({
      text: async () => "<GetRecordsResponse/>",
    });
    vi.stubGlobal("fetch", fetch);

    render(<CatalogueServiceClient />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    const url = new URL(fetch.mock.calls[0][0]);
    expect(url.protocol).toBe("https:");
    expect(url.searchParams.get("SERVICE")).toBe("CSW");
    expect(url.searchParams.get("REQUEST")).toBe("GetRecords");
    expect(url.searchParams.get("VERSION")).toBe("2.0.2");
    // The gmd output schema is a normative identifier and keeps its http
    // scheme - it names the schema of the answer, it is never requested.
    expect(url.searchParams.get("outputSchema")).toBe(
      "http://www.isotc211.org/2005/gmd",
    );
    expect(url.searchParams.get("typeNames")).toBe("gmd:MD_Metadata");
  });

  test("keeps the negotiated CSW parameters a client can replay", async () => {
    const fetch = vi.fn().mockResolvedValue({
      text: async () => "<GetRecordsResponse/>",
    });
    vi.stubGlobal("fetch", fetch);

    render(<CatalogueServiceClient />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    const url = new URL(fetch.mock.calls[0][0]);
    expect(url.searchParams.get("resultType")).toBe("results");
    expect(url.searchParams.get("elementSetName")).toBe("full");
    expect(url.searchParams.get("constraintLanguage")).toBe("FILTER");
    expect(Number(url.searchParams.get("maxRecords"))).toBeGreaterThan(0);
    expect(Number(url.searchParams.get("startPosition"))).toBeGreaterThan(0);
  });
});

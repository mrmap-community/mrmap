import { describe, expect, it } from "vitest";
import serviceListOptions, {
  SERVICE_LIST_PER_PAGE,
  SERVICE_LIST_SORT,
} from "./serviceListOptions";

const services = ["WebMapService", "WebFeatureService", "CatalogueService"];

describe("list configuration of a registered service", () => {
  it("pages and sorts the list of every service the same way", () => {
    for (const type of services) {
      expect(serviceListOptions({ type })).toMatchObject({
        perPage: SERVICE_LIST_PER_PAGE,
        sort: SERVICE_LIST_SORT,
      });
    }
  });

  it("names the sparse fieldset of a service by its json:api type", () => {
    const options = serviceListOptions({
      type: "CatalogueService",
      fields: ["runningHarvestingJob"],
    });
    expect(options.sparseFieldsets).toEqual([
      { type: "CatalogueService", fields: ["runningHarvestingJob"] },
    ]);
  });

  it("asks for nothing beyond the columns of a service without a row action", () => {
    // an empty sparse fieldset would suppress all attributes of the list answer
    expect(serviceListOptions({ type: "WebFeatureService" }).sparseFieldsets).toBeUndefined();
  });

  it("passes the row action of a service on as a component", () => {
    const HarvestButton = () => null;
    const options = serviceListOptions({ type: "CatalogueService", additionalActions: HarvestButton });
    expect(options.additionalActions).toBe(HarvestButton);
  });

  it("does not share the sort of two lists, which react admin stores per list", () => {
    const [webMapService, webFeatureService] = services.map((type) => serviceListOptions({ type }));
    expect(webMapService.sort).not.toBe(webFeatureService.sort);
  });
});

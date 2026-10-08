import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import CronInput from "../../../Input/CronInput";
import ServiceMetadataTab from "../../Generic/ServiceShow/ServiceMetadataTab";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";
import ServiceShow, {
  type ServiceTab,
} from "../../Generic/ServiceShow/ServiceShow";
import Overview from "./Overview";
import Records from "./Records";

const tabs: ServiceTab[] = [
  {
    path: "",
    label: "serviceShow.overview",
    icon: <AutoGraphIcon />,
    content: <Overview />,
  },
  {
    path: "metadata",
    label: "serviceShow.metadata",
    resource: "CatalogueService",
    operation: "partial_update_CatalogueService",
    content: <ServiceMetadataTab />,
  },
  {
    path: "CatalogueServiceOperationUrl/*",
    label: "serviceShow.operationUrls",
    resource: "CatalogueServiceOperationUrl",
    countSource: "operationUrls",
    operation: "list_related_CatalogueServiceOperationUrl_of_CatalogueService",
    content: (
      <ServiceRelatedTab
        resource="CatalogueServiceOperationUrl"
        defaultSelectedColumns={["operation", "url", "method"]}
      />
    ),
  },
  { path: "records/*", label: "serviceShow.records", content: <Records /> },
  {
    path: "HarvestingJob/*",
    label: "serviceShow.harvesting",
    resource: "HarvestingJob",
    operation: "list_related_HarvestingJob_of_CatalogueService",
    content: (
      <ServiceRelatedTab
        resource="HarvestingJob"
        realtime
        refetchInterval={20000}
        defaultSelectedColumns={[
          "id",
          "phase",
          "progress",
          "createdAt",
          "doneAt",
        ]}
      />
    ),
  },
  {
    path: "PeriodicHarvestingJob/*",
    label: "serviceShow.schedules",
    resource: "PeriodicHarvestingJob",
    operation: "list_related_PeriodicHarvestingJob_of_CatalogueService",
    content: (
      <ServiceRelatedTab
        resource="PeriodicHarvestingJob"
        defaultSelectedColumns={["enabled", "scheduling", "timeUntilNextRun"]}
        formFieldOverrides={[
          {
            component: CronInput,
            props: { source: "scheduling" },
          },
        ]}
      />
    ),
  },
];

export default function ShowCatalogueService() {
  return <ServiceShow tabs={tabs} />;
}

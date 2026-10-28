import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import CronInput from "../../../Input/CronInput";
import ServiceAttentionTab from "../../Generic/ServiceShow/ServiceAttentionTab";
import ServiceMetadataTab from "../../Generic/ServiceShow/ServiceMetadataTab";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";
import ServiceShow, {
  type ServiceTab,
} from "../../Generic/ServiceShow/ServiceShow";
import HarvestingScheduleWarnings from "./HarvestingScheduleWarnings";
import HarvestStepSizeField from "./HarvestStepSizeField";
import MonitoringTab from "./MonitoringTab";
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
    path: "alerts",
    label: "serviceShow.attention",
    icon: <WarningAmberIcon />,
    content: <ServiceAttentionTab />,
  },
  {
    path: "metadata",
    label: "serviceShow.metadata",
    resource: "CatalogueService",
    operation: "partial_update_CatalogueService",
    content: (
      <ServiceMetadataTab
        updateFieldDefinitions={[
          {
            component: HarvestStepSizeField,
            props: { source: "maxStepSize" },
          },
        ]}
      />
    ),
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
        header={<HarvestingScheduleWarnings />}
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
  {
    path: "CatalogueServiceMonitoringSetting/*",
    label: "serviceShow.monitoring",
    resource: "CatalogueServiceMonitoringSetting",
    countSource: "catalogueServiceMonitoringSettings",
    operation:
      "list_related_CatalogueServiceMonitoringSetting_of_CatalogueService",
    content: <MonitoringTab />,
  },
];

export default function ShowCatalogueService() {
  return <ServiceShow tabs={tabs} />;
}

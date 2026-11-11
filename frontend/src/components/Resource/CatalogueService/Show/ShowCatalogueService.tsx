import type { PropsWithChildren } from "react";
import { DateField, useRecordContext, useTranslate } from "react-admin";

import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Alert } from "@mui/material";

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

const HarvestingTab = ({ children }: PropsWithChildren) => {
  const service = useRecordContext();
  const translate = useTranslate();
  return service?.isHarvestable === false
    ? <Alert severity="info">{translate("harvestingSchedules.unavailable")}</Alert>
    : children;
};

/**
 * The runs of this catalogue. The moment a run was made is answered as `dateCreated`
 * - the tab declared it as `createdAt` for ages, a key no field of a harvesting job
 * answers, which left the column silently empty for every run (#1078). Its header is
 * titled through the translations here because the resource answers no titles of its
 * own yet (#1085), and a run whose start cannot be known shows the empty text.
 */
const HarvestingRunsTab = () => {
  const translate = useTranslate();
  return (
    <HarvestingTab>
      <ServiceRelatedTab
        resource="HarvestingJob"
        realtime
        refetchInterval={20000}
        defaultSelectedColumns={["id", "phase", "progress", "dateCreated", "doneAt"]}
        updateFieldDefinitions={[
          {
            component: DateField,
            props: {
              source: "dateCreated",
              label: translate("harvestingActivity.started"),
              showTime: true,
              emptyText: "—",
            },
          },
        ]}
      />
    </HarvestingTab>
  );
};

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
    content: <HarvestingRunsTab />,
  },
  {
    path: "PeriodicHarvestingJob/*",
    label: "serviceShow.schedules",
    resource: "PeriodicHarvestingJob",
    operation: "list_related_PeriodicHarvestingJob_of_CatalogueService",
    content: (
      <HarvestingTab>
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
      </HarvestingTab>
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

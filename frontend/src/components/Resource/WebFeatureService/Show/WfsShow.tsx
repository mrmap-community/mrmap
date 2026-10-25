import { useState } from "react";
import { UrlField, useRecordContext, useTranslate, type RaRecord } from "react-admin";

import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Grid, Stack, Typography } from "@mui/material";

import ConfigureRelatedResource from "../../../../jsonapi/components/ConfigureRelatedResource";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import AccessRulesSummary from "../../Generic/ServiceShow/AccessRulesSummary";
import ElementInspection from "../../Generic/ServiceShow/ElementInspection";
import ServiceAttentionTab from "../../Generic/ServiceShow/ServiceAttentionTab";
import ServiceMetadataTab from "../../Generic/ServiceShow/ServiceMetadataTab";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";
import ServiceShow, {
  type ServiceTab,
} from "../../Generic/ServiceShow/ServiceShow";
import { UpdateSettingTab } from "../../Generic/ServiceShow/UpdateSettingTab";
import MonitoringTab from "./Tabs/MonitoringTab";
import OverviewTab from "./Tabs/OverviewTab";

function OperationUrls() {
  const record = useRecordContext();
  const translate = useTranslate();
  const urls: { id: string; url?: string }[] = record?.operationUrls ?? [];
  return (
    <Stack spacing={2} sx={{ p: 2, overflowWrap: "anywhere" }}>
      {urls.length ? (
        urls.map(
          (url) =>
            url.url && <UrlField key={url.id} source="url" record={url} />,
        )
      ) : (
        <Typography>{translate("serviceShow.empty")}</Typography>
      )}
    </Stack>
  );
}

function AccessRules() {
  const record = useRecordContext();
  return (
    <Stack spacing={2}>
      <AccessRulesSummary
        ruleResource="AllowedWebFeatureServiceOperation"
        serviceId={record?.id}
      />
      <ServiceRelatedTab
        resource="AllowedWebFeatureServiceOperation"
        defaultSelectedColumns={[
          "operations",
          "description",
          "allowedGroups",
          "securedFeatureTypes",
        ]}
        formFieldOverrides={[
          {
            component: SchemaAutocompleteInput,
            props: {
              source: "securedFeatureTypes",
              relatedResource: { resource: "WebFeatureService", id: record?.id },
            },
          },
        ]}
      />
    </Stack>
  );
}

/**
 * Feature type rows next to the read oriented inspection of the clicked row,
 * so a user can read a feature type before opening its editor.
 */
function FeatureTypesTab() {
  const record = useRecordContext();
  const [selected, setSelected] = useState<RaRecord>();
  return (
    <Grid container spacing={2} sx={{ justifyContent: "space-between" }}>
      <Grid size={{ xs: 12, md: 7 }}>
        <ServiceRelatedTab
          resource="FeatureType"
          defaultSelectedColumns={["name", "title", "abstract"]}
          onRowClick={setSelected}
        />
      </Grid>
      <Grid size={{ xs: 12, md: 5 }}>
        <ElementInspection
          resource="FeatureType"
          id={selected?.id}
          serviceResource="WebFeatureService"
          serviceId={record?.id}
        />
      </Grid>
    </Grid>
  );
}

const tabs: ServiceTab[] = [
  {
    path: "",
    label: "serviceShow.overview",
    icon: <AutoGraphIcon />,
    content: (
      <OverviewTab/>
    ),
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
    resource: "WebFeatureService",
    operation: "partial_update_WebFeatureService",
    content: <ServiceMetadataTab />,
  },
  {
    path: "operationUrls",
    label: "serviceShow.operationUrls",
    countSource: "operationUrls",
    content: <OperationUrls />,
  },
  {
    path: "FeatureType/*",
    label: "serviceShow.featureTypes",
    resource: "FeatureType",
    countSource: "featuretypes",
    operation: "list_related_FeatureType_of_WebFeatureService",
    content: <FeatureTypesTab />,
  },
  {
    path: "ProxySetting",
    label: "serviceShow.proxy",
    operation:
      "list_related_WebFeatureServiceProxySetting_of_WebFeatureService",
    content: (
      <ConfigureRelatedResource relatedResource="WebFeatureServiceProxySetting" />
    ),
  },
  {
    path: "AllowedWebFeatureServiceOperation/*",
    label: "serviceShow.access",
    resource: "AllowedWebFeatureServiceOperation",
    operation:
      "list_related_AllowedWebFeatureServiceOperation_of_WebFeatureService",
    content: <AccessRules />,
  },
  {
    path: "WebFeatureServiceMonitoringSetting/*",
    label: "serviceShow.monitoring",
    resource: "WebFeatureServiceMonitoringSetting",
    countSource: "webFeatureServiceMonitoringSettings",
    operation:
      "list_related_WebFeatureServiceMonitoringSetting_of_WebFeatureService",
    content: <MonitoringTab />,
  },
  {
      path: "WebFeatureServiceUpdateSetting/*",
      label: "serviceShow.updates",
      resource: "WebFeatureServiceUpdateSetting",
      countSource: "webFeatureServiceUpdateSettings",
      operation: "list_related_WebFeatureServiceUpdateSetting_of_WebFeatureService",
      content: <UpdateSettingTab resource="WebFeatureServiceUpdateSetting" />,
    },
];

export default function WfsShow() {
  return <ServiceShow tabs={tabs} />;
}

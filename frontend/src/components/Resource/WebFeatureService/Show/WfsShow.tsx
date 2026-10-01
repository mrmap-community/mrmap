import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import { Stack, Typography } from "@mui/material";
import { UrlField, useRecordContext, useTranslate } from "react-admin";
import ConfigureRelatedResource from "../../../../jsonapi/components/ConfigureRelatedResource";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import ServiceMetadataTab from "../../Generic/ServiceShow/ServiceMetadataTab";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";
import ServiceShow, {
  type ServiceTab,
} from "../../Generic/ServiceShow/ServiceShow";
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
    content: (
      <ServiceRelatedTab
        resource="FeatureType"
        defaultSelectedColumns={["name", "title", "abstract"]}
      />
    ),
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
];

export default function WfsShow() {
  return <ServiceShow tabs={tabs} />;
}

import { Stack, Typography } from "@mui/material";
import { createElement } from "react";
import {
  Labeled,
  SimpleShowLayout,
  UrlField,
  useRecordContext,
  useResourceContext,
  useTranslate
} from "react-admin";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import { prepareGetCapabilititesUrl } from "../../../../ows-lib/OwsContext/utils";
import SimpleCard from "../../../MUI/SimpleCard";
import MapViewerButton from "../../WebMapService/Button/MapViewerButton";
import ActivateServiceButton from "./ActivateServiceButton";
import ServicePreviewImage from "./ServicePreviewImage";

export type ServiceProtocol = "WMS" | "WFS" | "CSW";

export function capabilitiesUrl(
  record: Record<string, unknown> | undefined,
  protocol: ServiceProtocol,
  version?: string,
): string | undefined {
  const urls = record?.operationUrls;
  if (!Array.isArray(urls)) return undefined;
  const endpoint = urls.find(
    (url) => url?.operation === 1 && url?.method === 1,
  );
  if (typeof endpoint?.url !== "string") return undefined;
  try {
    return prepareGetCapabilititesUrl(endpoint.url, protocol, version).href;
  } catch {
    return undefined;
  }
}

const ServiceDetailsCard = ({
  protocol,
}: {
  protocol: ServiceProtocol;
}) => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: `retrieve_${resource}`,
    forInput: false,
    ignoreId: false,
  });
  const versionField = fields.find((field) => field.props.source === "version");
  const choices = versionField?.props.choices as
    { id: unknown; name: string }[] | undefined;
  const version = choices?.find(
    (choice) => choice.id === record?.version,
  )?.name;
  const url = capabilitiesUrl(record, protocol, version);
  return (
    <SimpleCard
      title={translate("serviceShow.details")}
      cardProps={{
        variant: "outlined",
        sx: { width: "100%", minWidth: 0, height: "100%" },
      }}
      footer={
        record ? (
          <>
            {protocol === "WMS" && (
              <MapViewerButton
                key={record.id}
                label="serviceShow.openMapViewer"
                variant="outlined"
                sx={{ flex: 1, minWidth: 0 }}
              />
            )}
            <ActivateServiceButton />
          </>
        ) : undefined
      }
      footerProps={{ sx: { px: 2, pb: 2, gap: 1, flexWrap: "wrap" } }}
    >
      {record ? <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        {(protocol === "WMS" || protocol === "WFS") && (
          <ServicePreviewImage authenticated={protocol === "WFS"} />
        )}
        <SimpleShowLayout
          sx={{ p: 0, minWidth: 0, flex: 1, overflowWrap: "anywhere" }}
        >
          {["id", "title", "abstract", "version"].map((source) => {
            const field = fields.find(
              (candidate) => candidate.props.source === source,
            );
            return field
              ? createElement(field.component, { ...field.props, key: source })
              : null;
          })}
          {url && (
            <Labeled label="serviceShow.capabilities">
              <UrlField source="url" record={{ id: record?.id, url }} />
            </Labeled>
          )}
        </SimpleShowLayout>
      </Stack> : (
        <Typography variant="body2" color="text.secondary">
          {translate("serviceList.noSelection")}
        </Typography>
      )}
    </SimpleCard>
  );
};

export default ServiceDetailsCard;

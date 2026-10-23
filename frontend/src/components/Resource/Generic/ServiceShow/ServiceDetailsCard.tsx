import { createElement } from "react";
import {
  Labeled,
  ShowButton,
  SimpleShowLayout,
  UrlField,
  useRecordContext,
  useResourceContext,
  useTranslate
} from "react-admin";

import { Stack, Typography } from "@mui/material";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import { prepareGetCapabilititesUrl } from "../../../../ows-lib/OwsContext/utils";
import SimpleCard from "../../../MUI/SimpleCard";
import MapViewerButton from "../../WebMapService/Button/MapViewerButton";
import ActivateServiceButton from "./ActivateServiceButton";
import ServiceAlertChips from "./ServiceAlertChips";
import ServiceOutcomes from "./ServiceOutcomes";
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
  attention,
  openDetails,
}: {
  protocol: ServiceProtocol;
  /** the states of the service which need attention and the outcome of its last
   *  run and job, which the screen which only selects a service shows beside its
   *  identity - a screen which shows the service itself answers them apart */
  attention?: boolean;
  /** the way to the screen of the service, which the card of a service which is
   *  only selected cannot show by itself */
  openDetails?: boolean;
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
            {openDetails && (
              <ShowButton
                label="serviceShow.openDetails"
                variant="outlined"
                sx={{ flex: 1, minWidth: 0 }}
              />
            )}
            {protocol === "WMS" && (
              /* the capabilities URL of the map viewer lives in the state of the
                 button, so a new record must remount it - the open details button
                 above needs no key of its own: it answers its way from the record
                 context on every render and a second child of the same key as the
                 one of this button leaves an open details button of a selection
                 before behind */
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
            if (record[source] === undefined || record[source] === null || record[source] === "") return null;
            const field = fields.find(
              (candidate) => candidate.props.source === source,
            );
            return field
              ? createElement(field.component, {
                  ...field.props,
                  key: source,
                  label: translate(`serviceShow.fields.${source}`),
                })
              : null;
          })}
          {url && (
            <Labeled label="serviceShow.capabilities">
              <UrlField source="url" record={{ id: record?.id, url }} />
            </Labeled>
          )}
          {attention && (
            <Stack spacing={0.5} sx={{ pt: 1, minWidth: 0 }}>
              <Stack
                direction="row"
                spacing={0.5}
                sx={{ alignItems: "center", flexWrap: "wrap", gap: 0.5 }}
              >
                <ServiceAlertChips record={record} />
              </Stack>
              {/* the record of the last run and job belongs to one service, so a
                  new selection asks for the record of the service it names and
                  not for the record of the service before it */}
              <ServiceOutcomes key={`${resource}:${record.id}`} />
            </Stack>
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

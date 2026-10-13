import { Fragment } from "react";
import { Chip } from "@mui/material";
import { type RaRecord, useRecordContext, useTranslate } from "react-admin";
import { SERVICE_ALERTS } from "./ServiceAttentionTab";

export interface ServiceAlertChipsProps {
  /** the service to answer, the record of the screen if not given */
  record?: RaRecord;
}

/**
 * The states of a service which need attention, as compact chips.
 *
 * The same states the attention tab of a service lists (see SERVICE_ALERTS), but
 * short enough to be shown next to a service in a list. Nothing is asked from the
 * api: the states are attributes of the service which is shown, so a record which
 * does not answer an attribute is not counted for it - which keeps the chips of a
 * web map service free of the states only a catalogue has.
 */
const ServiceAlertChips = ({ record }: ServiceAlertChipsProps) => {
  // the record given by the caller wins: the record of the context is the one of
  // the surrounding screen, which is not necessarily the service asked for
  const contextService = useRecordContext<RaRecord>();
  const translate = useTranslate();
  const service = record ?? contextService;
  const alerts = SERVICE_ALERTS.filter((alert) =>
    Boolean(service?.[alert.flag]),
  );

  if (alerts.length === 0) {
    return (
      <Chip
        size="small"
        color="success"
        label={translate("serviceAttention.shortLabels.healthy")}
      />
    );
  }

  return (
    <Fragment>
      {alerts.map((alert) => (
        <Chip
          key={alert.flag}
          size="small"
          color={alert.severity}
          label={translate(`serviceAttention.shortLabels.${alert.flag}`)}
          title={translate(`serviceAttention.alerts.${alert.flag}`)}
        />
      ))}
    </Fragment>
  );
};

export default ServiceAlertChips;

import { Chip } from "@mui/material";
import { useFieldValue, useTranslate } from "react-admin";

export interface ServiceAlertSeverityFieldProps {
  source?: string;
}

const SEVERITY_COLORS: Record<string, "error" | "warning"> = {
  error: "error",
  warning: "warning",
};

/**
 * Shows how much attention a service needs as a chip.
 *
 * The api answers the severity by the name of its choice, so the names of the
 * severities are the keys of the translations of the attention.
 */
const ServiceAlertSeverityField = ({
  source = "severity",
}: ServiceAlertSeverityFieldProps) => {
  const severity = useFieldValue({ source }) as string | undefined;
  const translate = useTranslate();

  if (!severity) {
    return null;
  }

  return (
    <Chip
      size="small"
      color={SEVERITY_COLORS[severity] ?? "warning"}
      label={translate(`serviceAlerts.severity.${severity}`, { _: severity })}
    />
  );
};

export default ServiceAlertSeverityField;

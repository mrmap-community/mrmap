import { Typography } from "@mui/material";
import { useFieldValue, useTranslate } from "react-admin";

export interface ServiceAlertCategoryFieldProps {
  source?: string;
}

/**
 * Shows which state of a service needs attention.
 *
 * The api answers the state by the name of its choice, which is a long name
 * meant for machines, so it is translated here instead of answered as it is.
 */
const ServiceAlertCategoryField = ({
  source = "category",
}: ServiceAlertCategoryFieldProps) => {
  const category = useFieldValue({ source }) as string | undefined;
  const translate = useTranslate();

  if (!category) {
    return null;
  }

  return (
    <Typography
      variant="body2"
      component="span"
      title={category}
      data-category={category}
    >
      {translate(`serviceAlerts.category.${category}`, { _: category })}
    </Typography>
  );
};

export default ServiceAlertCategoryField;

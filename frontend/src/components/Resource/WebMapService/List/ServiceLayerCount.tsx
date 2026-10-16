import { Typography } from "@mui/material";
import type { RaRecord } from "react-admin";

export interface ServiceLayerCountProps {
  /** the service the layers are counted of, as the list of services answered it */
  service?: RaRecord;
}

/**
 * How many layers a service has, answered by the service itself.
 *
 * The api annotates a service with the count of its layers for a request which
 * names the attribute (registry/querys/explorer.py answers it in the query of the
 * page, so a whole page of services is one query and not a query per service). It
 * also answers the layers of a service as its related layers, which are part of
 * the sparse fieldset of the list too: a page which carries them but not the
 * annotation is counted by them.
 */
export const serviceLayerCount = (service?: RaRecord): number | undefined => {
  const counted = service?.elementCount;
  if (
    counted !== undefined &&
    counted !== null &&
    Number.isFinite(Number(counted))
  ) {
    return Number(counted);
  }
  return Array.isArray(service?.layers) ? service.layers.length : undefined;
};

/**
 * How many layers a service has, as a number of the row or the panel which shows
 * it. Nothing is asked from the api: the service of the row answers the count.
 */
const ServiceLayerCount = ({ service }: ServiceLayerCountProps) => {
  const count = serviceLayerCount(service);
  if (count === undefined) {
    return null;
  }
  return (
    <Typography variant="body2" component="span">
      {count}
    </Typography>
  );
};

export default ServiceLayerCount;

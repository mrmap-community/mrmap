import { Typography } from "@mui/material";
import type { RaRecord } from "react-admin";

export interface ServiceElementCountProps {
  /** the service the elements are counted of, as the list of services answered it */
  record?: RaRecord;
  /** the property which answers the elements of the service as a relationship,
   *  unset for a resource which does not answer them within its records */
  relation?: string;
}

/**
 * How many elements a service has - layers, feature types or records - answered
 * by the service itself.
 *
 * The api annotates a service with the count of its elements for a request
 * which names the attribute (registry/querys/explorer.py answers it in the query
 * of the page, so a whole page of services is one query and not a query per
 * service, for every kind of service). The api also answers the elements of a
 * web map service and of a web feature service as their related layers and
 * feature types, which are part of the sparse fieldset of these lists: a page
 * which carries them but not the annotation is counted by them.
 */
export const serviceElementCount = (
  record?: RaRecord,
  relation?: string,
): number | undefined => {
  const counted = record?.elementCount;
  if (
    counted !== undefined &&
    counted !== null &&
    Number.isFinite(Number(counted))
  ) {
    return Number(counted);
  }
  const elements = relation === undefined ? undefined : record?.[relation];
  return Array.isArray(elements) ? elements.length : undefined;
};

/**
 * How many elements a service has, as a number of the row or the panel which
 * shows it. Nothing is asked from the api: the service of the row answers the
 * count.
 */
const ServiceElementCount = ({
  record,
  relation,
}: ServiceElementCountProps) => {
  const count = serviceElementCount(record, relation);
  if (count === undefined) {
    return null;
  }
  return (
    <Typography variant="body2" component="span">
      {count}
    </Typography>
  );
};

export default ServiceElementCount;

import { type ReactNode } from "react";
import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { RelatedResource } from "../../../providers/dataProvider";
import RelatedResourceField from "../../Field/RelatedResourceField";
import ServiceAlertCategoryField from "./ServiceAlertCategoryField";
import ServiceAlertSeverityField from "./ServiceAlertSeverityField";

/** the interval the attention of a service is asked for again, in milliseconds */
export const ALERTS_REFETCH_INTERVAL = 60000;

export interface ListServiceAlertProps {
  /** the service whose alerts are listed */
  relatedResource?: Partial<RelatedResource>;
}

/**
 * The states of one service which need the attention of an administrator.
 *
 * An alert is not stored but derived from the runs and jobs of the service,
 * which means two things for this list: it cannot be pushed by the realtime bus,
 * because there is no row which changes, and an alert disappears by itself as
 * soon as the state behind it is fixed - so the list only has to ask again.
 *
 * The endpoint answers the alerts of the service with the worst one first, which
 * is the order this list shows them in.
 */
const ListServiceAlert = ({
  relatedResource,
}: ListServiceAlertProps): ReactNode => (
  <ListGuesser
    resource="ServiceAlert"
    relatedResource={relatedResource}
    // react-admin answers a string title by its translation, which is the name
    // the attention of a service is listed under
    title="serviceAlerts.title"
    // the attention of a service starts with what hurts most: the errors before
    // the warnings, which is the order the endpoint answers by default too
    sort={{ field: "severity", order: "ASC" }}
    perPage={25}
    defaultSelectedColumns={[
      "severity",
      "category",
      "message",
      "resource",
      "occurredAt",
    ]}
    updateFieldDefinitions={[
      {
        component: ServiceAlertSeverityField,
        props: { source: "severity" },
      },
      {
        component: ServiceAlertCategoryField,
        props: { source: "category" },
      },
      {
        component: RelatedResourceField,
        props: { source: "service" },
      },
      {
        component: RelatedResourceField,
        props: { source: "resource" },
      },
    ]}
    refetchInterval={ALERTS_REFETCH_INTERVAL}
  />
);

export default ListServiceAlert;

import { type ListProps } from "react-admin";
import ServiceList from "../../Generic/ServiceList/ServiceList";
import { type ServiceListConfig } from "../../Generic/ServiceList/config";

/**
 * The attributes the list of registered web map services answers, as the api
 * names them in a sparse fieldset.
 *
 * The list shows a service as a row and not as a table of every column, so it
 * asks only for what a row and the details panel of a selected service show. The
 * states of attention are asked apart from the columns a service is stored with,
 * because the api answers them by a subquery per state and only for the states a
 * request names - see registry/querys/alerts.py. The count of the layers and the
 * layers themselves are named for the same reason: the api annotates a service
 * with them in the query which answers the page of services, and only for a
 * request which names them - see registry/querys/explorer.py. The secured
 * capabilities url and the security of a service are answered by a web map
 * service only.
 */
export const WEB_MAP_SERVICE_LIST_FIELDS = [
  "id",
  "title",
  "abstract",
  "string_representation",
  "hits",
  "date_stamp",
  "is_active",
  "is_secured",
  "xml_backup_file_secured",
  "created_at",
  "last_modified_at",
  "has_alert",
  "monitoring_failed",
  "monitoring_failed_at",
  "update_review_required",
  "update_review_required_at",
  "update_failed",
  "update_failed_at",
  "element_count",
  "layers",
  "preview_url",
];

/** what the list of registered web map services asks apart from the other kinds */
export const WMS_SERVICE_LIST_CONFIG: ServiceListConfig = {
  resource: "WebMapService",
  protocol: "WMS",
  countLabelKey: "layers",
  countRelation: "layers",
  fields: WEB_MAP_SERVICE_LIST_FIELDS,
};

/**
 * The screen which lists the registered web map services.
 */
const ListWebMapService = (props: Partial<ListProps>) => (
  <ServiceList {...props} config={WMS_SERVICE_LIST_CONFIG} />
);

export default ListWebMapService;

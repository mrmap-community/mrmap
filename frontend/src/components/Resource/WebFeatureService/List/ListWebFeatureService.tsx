import type { ReactNode } from "react";
import { ListProps } from "react-admin";

import { type ServiceListConfig } from "../../Generic/ServiceList/config";
import ServiceList from "../../Generic/ServiceList/ServiceList";

/**
 * The attributes the list of registered web feature services answers, as the api
 * names them in a sparse fieldset.
 *
 * The list shows a service as a row and not as a table of every column, so it
 * asks only for what a row and the details panel of a selected service show -
 * see the list of registered web map services for why the states of attention
 * and the count of the feature types are named apart from the columns a service
 * is stored with (registry/querys/alerts.py and registry/querys/explorer.py).
 * The preview image of a web feature service is rendered by the api and asked
 * authenticated; the security attributes of a web map service are not answered
 * for a web feature service.
 */
export const WEB_FEATURE_SERVICE_LIST_FIELDS = [
  "id",
  "title",
  "abstract",
  "string_representation",
  "hits",
  "date_stamp",
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
  "featuretypes",
  "preview_url",
];

/** what the list of registered web feature services asks apart from the other kinds */
export const WFS_SERVICE_LIST_CONFIG: ServiceListConfig = {
  resource: "WebFeatureService",
  protocol: "WFS",
  countLabelKey: "featureTypes",
  countRelation: "featuretypes",
  fields: WEB_FEATURE_SERVICE_LIST_FIELDS,
};

/**
 * The screen which lists the registered web feature services.
 *
 * The create and edit dialogs of the resource stay routed through the
 * ListWithDialogs, which renders the generic list with these props and the
 * routes of the dialogs beside it.
 */
const ListWebFeatureService = (props: Partial<ListProps>): ReactNode => (
  <ServiceList
    {...props}
    config={WFS_SERVICE_LIST_CONFIG}
  />
);

export default ListWebFeatureService;

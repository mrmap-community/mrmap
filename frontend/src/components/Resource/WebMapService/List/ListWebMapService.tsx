import { type ListProps, SearchInput } from "react-admin";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import WmsServiceExplorer from "./WmsServiceExplorer";

/**
 * The attributes the list of registered services answers, as the api names them
 * in a sparse fieldset.
 *
 * The list shows a service as a row and not as a table of every column, so it
 * asks only for what a row and the details panel of a selected service show. The
 * states of attention are asked apart from the columns a service is stored with,
 * because the api answers them by a subquery per state and only for the states a
 * request names - see registry/querys/alerts.py. The count of the layers and the
 * layers themselves are named for the same reason: the api annotates a service
 * with them in the query which answers the page of services, and only for a
 * request which names them - see registry/querys/explorer.py.
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

/** the columns of this list are fixed by the rows, so none of them is chosen */
const WmsListActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

/**
 * The screen which lists the registered web map services.
 *
 * The search is always on, because the list of services of a running deployment
 * is navigated by looking for a title, an abstract or a keyword of a service.
 */
const ListWebMapService = (props: Partial<ListProps>) => (
  <ListGuesser
    {...props}
    additionalFilters={[<SearchInput key="search" source="search" alwaysOn />]}
    perPage={25}
    sort={{ field: "title", order: "ASC" }}
    aside={false}
    // the sparse fieldset of a resource is asked by the options of the query and
    // not by a prop of the list: only the options of the query reach the request
    // (see providers/dataProvider.ts)
    queryOptions={{
      meta: {
        jsonApiParams: {
          "fields[WebMapService]": WEB_MAP_SERVICE_LIST_FIELDS.join(","),
        },
      },
    }}
    // the screen itself answers a view without services, so the facets and the
    // search stay usable when a facet or the search narrows the list to none
    empty={<WmsServiceExplorer />}
    ActionsComponent={WmsListActions}
    listContent={<WmsServiceExplorer />}
  />
);

export default ListWebMapService;

import { type ListProps, SearchInput } from "react-admin";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import WmsServiceExplorer from "./WmsServiceExplorer";

/**
 * The attributes the list of registered services answers, as the api names them.
 *
 * The list shows a service as a row and not as a table of every column, so it
 * asks only for what a row and the details panel of a selected service show. The
 * states of attention are asked apart from the columns a service is stored with,
 * because the api answers them by a subquery per state and only for the states a
 * request names - see registry/querys/alerts.py.
 */
export const WEB_MAP_SERVICE_LIST_FIELDS = [
  "id",
  "title",
  "abstract",
  "stringRepresentation",
  "hits",
  "dateStamp",
  "isActive",
  "isSecured",
  "xmlBackupFileSecured",
  "createdAt",
  "lastModifiedAt",
  "hasAlert",
  "monitoringFailed",
  "monitoringFailedAt",
  "updateReviewRequired",
  "updateReviewRequiredAt",
  "updateFailed",
  "updateFailedAt",
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
    // the screen itself answers a view without services, so the facets and the
    // search stay usable when a facet or the search narrows the list to none
    empty={<WmsServiceExplorer />}
    ActionsComponent={WmsListActions}
    listContent={<WmsServiceExplorer />}
  />
);

export default ListWebMapService;

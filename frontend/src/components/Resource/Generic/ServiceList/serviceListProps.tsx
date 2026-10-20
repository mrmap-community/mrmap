import { BooleanInput, type ListProps, SearchInput } from "react-admin";
import type { ListGuesserProps } from "../../../../jsonapi/components/ListGuesser";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import ServiceListAside from "./ServiceListAside";
import { type ServiceListConfig } from "./config";

/** the rows of a screen of services are navigated page by page */
export const SERVICE_LIST_PER_PAGE = 25;

/** the order a screen of services starts at - the api orders every kind of
 *  service by the title of its services (registry/views/service.py) */
export const SERVICE_LIST_SORT: NonNullable<Partial<ListProps>["sort"]> = {
  field: "title",
  order: "ASC",
};

/** the columns of these lists are fixed by the rows, so none of them is chosen */
const ServiceListActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

/**
 * The props which turn the generic list of a resource into the screen of the
 * registered services of that resource.
 *
 * The search is always on, because the list of services of a running deployment
 * is navigated by looking for a title, an abstract or a keyword of a service.
 * The screen itself answers a view without services, so the facets and the
 * search stay usable when a facet or the search narrows the list to none. The
 * sparse fieldset of a resource is asked by the options of the query and not by
 * a prop of the list: only the options of the query reach the request (see
 * providers/dataProvider.ts). The attributes it names are the ones the rows and
 * the details panel show, the states of attention which the facets and the tiles
 * filter and count, and the count of the elements of a service which the api
 * annotates for a request which names it - so no row asks anything of itself.
 *
 * The caller renders these props on the ListGuesser directly or through the
 * ListWithDialogs, which keeps the routes of the create and edit dialogs of the
 * resource alive beside the list.
 */
export const serviceListProps = (
  config: ServiceListConfig,
): ListGuesserProps => ({
  additionalFilters: [
    {component: SearchInput, props: {source: "search", alwaysOn: true}},
    {component: BooleanInput, props: {source: "has_alert", alwaysOn: true}},
  ],
  perPage: SERVICE_LIST_PER_PAGE,
  sort: SERVICE_LIST_SORT,
  
  queryOptions: {
    meta: {
      jsonApiParams: {
        [`fields[${config.resource}]`]: config.fields.join(","),
      },
    },
  },
  //empty: <ServiceListExplorer config={config} />,
  ActionsComponent: ServiceListActions,
  aside: <ServiceListAside protocol={config.protocol} />
        
  //listContent: <ServiceListExplorer config={config} />,
});

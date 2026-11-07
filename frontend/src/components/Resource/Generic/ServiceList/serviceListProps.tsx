import type { ListGuesserProps } from "../../../../jsonapi/components/ListGuesser";

import {
  BooleanInput,
  type ListProps,
  NumberField,
  SearchInput,
  TextField,
  WrapperField,
} from "react-admin";

import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import ServiceAlertChips from "../ServiceShow/ServiceAlertChips";
import { type ServiceListConfig } from "./config";
import ServiceListAside from "./ServiceListAside";
import ServiceRunState from "./ServiceRunState";

/** the rows of a screen of services are navigated page by page */
export const SERVICE_LIST_PER_PAGE = 25;

/** the order a screen of services starts at - the api orders every kind of
 *  service by the title of its services (registry/views/service.py) */
export const SERVICE_LIST_SORT: NonNullable<Partial<ListProps>["sort"]> = {
  field: "title",
  order: "ASC",
};

/** the states of attention which the column of the harvesting answers */
const HARVEST_STATE_FLAGS = ["harvestAborted", "harvestIncomplete"];

/** the states of attention which the column of the updates answers */
const UPDATE_STATE_FLAGS = ["updateFailed", "updateReviewRequired"];

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
 * A column which shows a state of a service shows the moment the run which
 * decided that state ended at, which the same annotation answers: a page of
 * twenty five services costs no request per row for a moment the page already
 * names. The columns of the updates and of the harvesting are therefore read
 * from the row (`ServiceRunState`), and the way to a single record behind a
 * state is the attention tab of that service, which has the one service in hand.
 *
 * A column is sorted only where the view of the api orders by its attribute
 * (`ordering_fields`, registry/views/service.py): the flag which answers the
 * attention of a service and the moment the harvesting failed are ordered, the
 * count of the elements of a service is not - and a column which answers two
 * annotations, as the column of the updates does, is not ordered by only one of
 * them.
 *
 * The caller renders these props on the ListGuesser directly or through the
 * ListWithDialogs, which keeps the routes of the create and edit dialogs of the
 * resource alive beside the list.
 */
export const serviceListProps = (
  config: ServiceListConfig,
  locale?: string,
): ListGuesserProps => ({
  sx: { '& .RaList-main': { minWidth: 0 } },
  columns: [
    <TextField key="title" source="title" label="serviceList.columns.title" sx={{ fontWeight: 600 }} />,
    <TextField
      key="abstract"
      source="abstract"
      label="serviceList.columns.abstract"
      sx={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}
    />,
    <TextField key="id" source="id" label="serviceList.columns.id" sx={{ overflowWrap: "anywhere" }} />,
    <WrapperField key="status" source="hasAlert" label="serviceList.columns.status" sortable>
      <ServiceAlertChips />
    </WrapperField>,
    // the states of the harvesting are answered by a catalogue only, so the
    // column is there where the config names the filters of the harvesting
    ...(config.harvestFilters
      ? [
          <WrapperField
            key="harvest"
            source="harvestFailedAt"
            label="serviceList.columns.harvest"
            sortable
          >
            <ServiceRunState
              flags={HARVEST_STATE_FLAGS}
              running={{
                source: "runningHarvestingJob",
                resource: "HarvestingJob",
                label: "serviceAttention.records.HarvestingJob",
              }}
              locales={locale}
            />
          </WrapperField>,
        ]
      : []),
    <NumberField
      key="count"
      source="elementCount"
      label={`serviceList.columns.${config.countLabelKey}`}
      sortable={false}
      emptyText="—"
    />,
    <WrapperField
      key="lastUpdate"
      source="updateFailedAt"
      label="serviceList.columns.lastUpdate"
      sortable={false}
    >
      <ServiceRunState flags={UPDATE_STATE_FLAGS} locales={locale} />
    </WrapperField>,
  ],
  dataGridProps: {
    bulkActionButtons: config.BulkActions ? <config.BulkActions /> : false,
    isRowSelectable: config.isRowSelectable,
    sx: {
      '& .RaDatagrid-tableWrapper': { maxWidth: "100%", overflowX: "auto" },
      '& .RaDatagrid-table': { minWidth: 1000 },
      '& .RaDatagrid-headerCell': { whiteSpace: "nowrap" },
      '& .column-title': { minWidth: 140 },
      '& .column-abstract': { minWidth: 180, maxWidth: 260, overflowWrap: "anywhere" },
      '& .column-id': { minWidth: 140, maxWidth: 180 },
      '& .RaDatagrid-rowCell:last-child': { whiteSpace: "nowrap" },
      '& .RaDatagrid-rowCell:last-child .MuiButton-root': { fontSize: 0, minWidth: 32, p: 0.75 },
      '& .RaDatagrid-rowCell:last-child .MuiButton-startIcon': { m: 0 },
    },
  },
  additionalFilters: [
    {component: SearchInput, props: {source: "search", alwaysOn: true}},
    {component: BooleanInput, props: {source: "has_alert", alwaysOn: true}},
  ],
  perPage: SERVICE_LIST_PER_PAGE,
  sort: SERVICE_LIST_SORT,
  additionalActions: config.RowAction ? <config.RowAction /> : undefined,
  
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

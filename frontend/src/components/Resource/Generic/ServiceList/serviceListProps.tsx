import type { ListGuesserProps } from "../../../../jsonapi/components/ListGuesser";

import {
  BooleanInput,
  DateField,
  FunctionField,
  type ListProps,
  NumberField,
  type RaRecord,
  ReferenceManyField,
  SearchInput,
  SingleFieldList,
  TextField,
  WrapperField,
} from "react-admin";

import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import ServiceAlertChips from "../ServiceShow/ServiceAlertChips";
import { type ServiceListConfig } from "./config";
import ServiceListAside from "./ServiceListAside";

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
    <WrapperField key="status" source="hasAlert" label="serviceList.columns.status" sortable={false}>
      <ServiceAlertChips />
    </WrapperField>,
    <NumberField
      key="count"
      source="elementCount"
      label={`serviceList.columns.${config.countLabelKey}`}
      sortable={false}
      emptyText="—"
    />,
    <FunctionField<RaRecord>
      key="lastUpdate"
      label="serviceList.columns.lastUpdate"
      sortable={false}
      render={record => (
        <ReferenceManyField
          reference={`${config.resource}UpdateJob`}
          target="service"
          source="id"
          filter={{ service: record.id, done_at__isnull: false }}
          sort={{ field: "doneAt", order: "DESC" }}
          perPage={1}
          queryOptions={{
            meta: {
              jsonApiParams: {
                [`fields[${config.resource}UpdateJob]`]: "id,done_at,status",
              },
            },
          }}
        >
          <SingleFieldList
            linkType={false}
            direction="column"
            sx={{ gap: 0 }}
            empty={<TextField source="doneAt" record={{ id: record.id, doneAt: undefined }} emptyText="serviceList.noUpdates" />}
          >
            <WrapperField>
              <DateField
                source="doneAt"
                showTime
                locales={locale === "en" ? "en-GB" : locale}
                options={{ day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }}
                sx={{ display: "block", whiteSpace: "nowrap" }}
              />
              <TextField source="status" sx={{ display: "block", color: "text.secondary" }} />
            </WrapperField>
          </SingleFieldList>
        </ReferenceManyField>
      )}
    />,
  ],
  dataGridProps: {
    bulkActionButtons: config.BulkActions ? <config.BulkActions /> : false,
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

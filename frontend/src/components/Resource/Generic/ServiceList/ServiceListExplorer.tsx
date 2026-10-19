import VpnLockIcon from "@mui/icons-material/VpnLock";
import {
  Box,
  Chip,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState, type MouseEvent } from "react";
import {
  DateField,
  EditButton,
  RecordContext,
  RecordContextProvider,
  ShowButton,
  useListContext,
  useTranslate,
  type Identifier,
} from "react-admin";
import ServiceAlertChips from "../ServiceShow/ServiceAlertChips";
import ServiceDetailsCard from "../ServiceShow/ServiceDetailsCard";
import { type ServiceListConfig } from "./config";
import ServiceElementCount from "./ServiceElementCount";
import ServiceSummaryTiles from "./ServiceSummaryTiles";
import { facetOf, filterForFacet, STATUS_FACETS } from "./alertFacets";

export interface ServiceHeaderCellProps {
  /** the label of the column, translated by the caller */
  label: string;
  /** the attribute the column is ordered by, unset for a column which cannot be */
  field?: string;
  /** how the values of the column are aligned */
  align?: "left" | "right";
}

/**
 * The head cell of a column of the list of services.
 *
 * A column which orders the list is clicked on its title, like in the table of
 * every other list of the application: the label shows the direction the list is
 * ordered by and turns it around when the same title is clicked again.
 *
 * A column is ordered only when the api orders a list of services by its
 * attribute, which the view of the api answers as ordering_fields
 * (registry/views/service.py) - the count of the layers and the moment a service
 * was modified last are not among them, so their columns name no field.
 */
const ServiceHeaderCell = ({
  label,
  field,
  align = "left",
}: ServiceHeaderCellProps) => {
  const { sort, setSort } = useListContext();
  const translate = useTranslate();
  const order = sort.field === field && sort.order === "ASC" ? "DESC" : "ASC";

  const sortBy = (event: MouseEvent) => {
    event.stopPropagation();
    if (field === undefined) {
      return;
    }
    setSort({ field, order });
  };

  return (
    <TableCell
      align={align}
      variant="head"
      sx={{ fontWeight: 600, whiteSpace: "nowrap" }}
    >
      {field === undefined ? (
        label
      ) : (
        <Tooltip
          title={translate("ra.sort.sort_by", {
            field_lower_first: field,
            order: translate(`ra.sort.${order}`),
          })}
          placement={align === "right" ? "bottom-end" : "bottom-start"}
          enterDelay={300}
        >
          <TableSortLabel
            active={sort.field === field}
            direction={sort.order === "ASC" ? "asc" : "desc"}
            onClick={sortBy}
          >
            {label}
          </TableSortLabel>
        </Tooltip>
      )}
    </TableCell>
  );
};

/**
 * The list of registered services of one kind of service.
 *
 * The tiles above the rows, the facet below the headline and the rows themselves
 * are three looks at one question - which services need attention - so all of
 * them are answered by the filters of the list and not by counts of their own.
 * The service which is selected is shown beside the rows. What differs between
 * the kinds of service - the resource the api is asked for, the label and the
 * source of the count of the elements of a service, the protocol of the details
 * panel and the action which the rows answer apart - is configured.
 */
export const ServiceListExplorer = ({
  config,
}: {
  config: ServiceListConfig;
}) => {
  const {
    data = [],
    total,
    isPending,
    filter,
    filterValues,
    displayedFilters,
    setFilters,
  } = useListContext();
  const translate = useTranslate();
  const [selected, setSelected] = useState<Identifier>();

  // a service which is not part of the answer any more cannot be selected
  useEffect(() => {
    if (
      selected !== undefined &&
      !data.some((record) => record.id === selected)
    ) {
      setSelected(undefined);
    }
  }, [data, selected]);

  const service = useMemo(
    () => data.find((record) => record.id === selected),
    [data, selected],
  );

  /**
   * The filters of the list narrowed to one facet.
   *
   * The filters which are stored are narrowed and not the filters of the query,
   * because the list answers its own filter with them and a facet must not carry
   * that one. The filters which are displayed are given untouched: a facet
   * changes which services the list answers and nothing of the form of filters
   * the user opened with the filter button.
   */
  const chooseFacet = (key: string) =>
    setFilters(filterForFacet(filterValues, key), displayedFilters);

  /**
   * A group which narrows exclusively answers the click on the facet which is
   * already chosen with no key at all - which is what a click on all has to be
   * too, because all is chosen while filters of the filter button or of a search
   * are still set. So the missing key ends the narrowing on all services and
   * every click on all resets the filters, also when all is already lit.
   */
  const changeFacet = (_: unknown, key: string | null) =>
    chooseFacet(key ?? "all");

  return (
    <Stack spacing={2} sx={{ p: 2 }}>
      <Stack
        direction="row"
        sx={{
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 1,
        }}
      >
        <Box>
          <Typography variant="h5">{translate("serviceList.title")}</Typography>
          <Typography variant="body2" color="text.secondary">
            {translate("serviceList.count", { count: total ?? 0 })}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={facetOf(filter)}
            onChange={changeFacet}
            aria-label={translate("serviceList.facetGroup")}
          >
            {STATUS_FACETS.map((facet) => (
              <ToggleButton key={facet.key} value={facet.key}>
                {translate(`serviceList.facets.${facet.key}`)}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
      </Stack>
      <ServiceSummaryTiles resource={config.resource} />
      <Box
        sx={{
          display: "grid",
          gap: 3,
          alignItems: "start",
          gridTemplateColumns: {
            xs: "1fr",
            lg: "minmax(0, 2fr) minmax(340px, 1fr)",
          },
        }}
      >
        <TableContainer
          sx={{
            maxHeight: 720,
            overflowY: "auto",
            bgcolor: "background.paper",
          }}
        >
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <ServiceHeaderCell
                  label={translate("serviceList.columns.service")}
                  field="title"
                />
                <ServiceHeaderCell
                  label={translate("serviceList.columns.status")}
                  field="has_alert"
                />
                <ServiceHeaderCell
                  label={translate(
                    `serviceList.columns.${config.countLabelKey}`,
                  )}
                  align="right"
                />
                <ServiceHeaderCell
                  label={translate("serviceList.columns.hits")}
                  align="right"
                  field="hits"
                />
                <ServiceHeaderCell
                  label={translate("serviceList.columns.modified")}
                />
                <ServiceHeaderCell
                  label={translate("serviceList.columns.actions")}
                />
              </TableRow>
            </TableHead>
            <TableBody>
              {isPending && data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <LinearProgress />
                  </TableCell>
                </TableRow>
              )}
              {!isPending && data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography variant="body2" color="text.secondary">
                      {translate("serviceList.empty")}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {data.map((record) => (
                <TableRow
                  key={record.id}
                  hover
                  selected={selected === record.id}
                  onClick={() => setSelected(record.id)}
                  sx={{ verticalAlign: "top" }}
                >
                  <TableCell sx={{ minWidth: 240 }}>
                    <Stack spacing={0.5}>
                      <Typography
                        variant="subtitle2"
                        color="primary"
                        sx={{ fontWeight: 600, overflowWrap: "anywhere" }}
                      >
                        {record.title ||
                          record.stringRepresentation ||
                          record.id}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {record.abstract}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ overflowWrap: "anywhere" }}
                      >
                        {record.id}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Stack
                      direction="row"
                      spacing={0.5}
                      sx={{ alignItems: "center", flexWrap: "wrap", gap: 0.5 }}
                    >
                      <ServiceAlertChips record={record} />
                      {Boolean(record?.isSecured) && (
                        <Chip
                          size="small"
                          variant="outlined"
                          color="warning"
                          icon={<VpnLockIcon />}
                          label={translate("serviceList.secured")}
                        />
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <ServiceElementCount
                      record={record}
                      relation={config.countRelation}
                    />
                  </TableCell>
                  <TableCell align="right">{record.hits ?? 0}</TableCell>
                  <TableCell>
                    <DateField source="lastModifiedAt" record={record} />
                  </TableCell>
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <RecordContextProvider value={record}>
                      <Stack direction="row" spacing={0.5}>
                        <ShowButton />
                        <EditButton />
                        {config.RowAction && <config.RowAction />}
                      </Stack>
                    </RecordContextProvider>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <RecordContext value={service}>
          <ServiceDetailsCard protocol={config.protocol} />
        </RecordContext>
      </Box>
    </Stack>
  );
};

export default ServiceListExplorer;

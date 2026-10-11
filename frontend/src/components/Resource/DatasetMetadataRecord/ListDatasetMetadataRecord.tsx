import {
  Box,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemButton,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import {
  DateField,
  EditButton,
  type Identifier,
  type ListProps,
  RecordContextProvider,
  ShowButton,
  SortButton,
  SearchInput,
  useListContext,
  useTranslate,
} from "react-admin";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../Lists/CustomListActions";
import ListGuesser from "../../../jsonapi/components/ListGuesser";
import DatasetCoverageMap from "./DatasetCoverageMap";
import { getCoverageBounds } from "./coverage";

const ExplorerActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

export const DatasetExplorer = () => {
  const { data = [], total, isPending } = useListContext();
  const translate = useTranslate();
  const [view, setView] = useState("split");
  const [selected, setSelected] = useState<Identifier>();
  const entries = useMemo(
    () =>
      data.flatMap((record) => {
        const bounds = getCoverageBounds(record.boundingGeometry);
        return bounds ? [{ record, bounds }] : [];
      }),
    [data],
  );
  useEffect(() => {
    if (
      selected !== undefined &&
      !data.some((record) => record.id === selected)
    )
      setSelected(undefined);
  }, [data, selected]);
  // Keep keyboard and map selection visible in the compact result list.
  useEffect(() => {
    if (selected !== undefined)
      document
        .getElementById(`dataset-result-${selected}`)
        ?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [selected]);

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
          <Typography variant="h5">
            {translate("datasetExplorer.title")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {translate("datasetExplorer.count", { count: total ?? 0 })}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <SortButton fields={["title", "dateStamp"]} />
          <ToggleButtonGroup
            exclusive
            value={view}
            size="small"
            onChange={(_, value: string | null) => value && setView(value)}
            aria-label={translate("datasetExplorer.view")}
          >
            {["list", "split", "map"].map((mode) => (
              <ToggleButton key={mode} value={mode}>
                {translate(`datasetExplorer.${mode}`)}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
      </Stack>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            md: view === "split" ? "minmax(0, 1fr) minmax(0, 1fr)" : "1fr",
          },
          gap: 3,
        }}
      >
        {view !== "map" && (
          <List
            disablePadding
            sx={{
              maxHeight: view === "split" ? 680 : undefined,
              overflowY: "auto",
            }}
            aria-label={translate("datasetExplorer.results")}
          >
            {!isPending && !data.length && (
              <Typography sx={{ p: 2 }}>
                {translate("ra.navigation.no_results")}
              </Typography>
            )}
            {data.map((record) => (
              <RecordContextProvider key={record.id} value={record}>
                <ListItem
                  id={`dataset-result-${record.id}`}
                  disablePadding
                  sx={{ display: "block" }}
                >
                  <ListItemButton
                    selected={selected === record.id}
                    onClick={() => setSelected(record.id)}
                    sx={{ alignItems: "flex-start", borderRadius: 1 }}
                  >
                    <Stack spacing={1} sx={{ minWidth: 0, width: "100%" }}>
                      <Typography
                        variant="subtitle1"
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
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {record.abstract}
                      </Typography>
                      <Stack
                        direction="row"
                        spacing={1}
                        sx={{ alignItems: "center", flexWrap: "wrap" }}
                      >
                        <Chip
                          size="small"
                          variant="outlined"
                          color={
                            entries.some(
                              (entry) => entry.record.id === record.id,
                            )
                              ? "primary"
                              : "default"
                          }
                          label={translate(
                            entries.some(
                              (entry) => entry.record.id === record.id,
                            )
                              ? "datasetExplorer.hasCoverage"
                              : "datasetExplorer.missingCoverage",
                          )}
                        />
                        <DateField source="dateStamp" />
                      </Stack>
                    </Stack>
                  </ListItemButton>
                  <Stack direction="row" sx={{ px: 1, pb: 1 }}>
                    <ShowButton />
                    <EditButton />
                  </Stack>
                </ListItem>
                <Divider component="li" />
              </RecordContextProvider>
            ))}
          </List>
        )}
        {view !== "list" && (
          <DatasetCoverageMap
            entries={entries}
            selected={selected}
            onSelect={setSelected}
          />
        )}
      </Box>
    </Stack>
  );
};

const ListDatasetMetadataRecord = (props: Partial<ListProps>) => (
  <ListGuesser
    {...props}
    additionalFilters={[<SearchInput key="search" source="search" alwaysOn />]}
    perPage={10}
    sort={{ field: "title", order: "ASC" }}
    aside={false}
    ActionsComponent={ExplorerActions}
    queryOptions={{
      meta: {
        jsonApiParams: {
          "fields[DatasetMetadataRecord]":
            "id,title,abstract,bounding_geometry,date_stamp",
        },
      },
    }}
    listContent={<DatasetExplorer />}
  />
);

export default ListDatasetMetadataRecord;

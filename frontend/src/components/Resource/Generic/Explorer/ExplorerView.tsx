import { useEffect, useMemo, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import {
  DateField,
  EditButton,
  type Identifier,
  type RaRecord,
  RecordContextProvider,
  ShowButton,
  SortButton,
  useListContext,
  useTranslate,
} from "react-admin";

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

import { getCoverageBounds } from "./coverage";
import CoverageMap, { type CoverageMapProps } from "./CoverageMap";
export const ExplorerView = ({
  geometrySource = "boundingGeometry",
  namespace = "datasetExplorer",
  showDetails = true,
  rowDetails,
  rowActions,
  rowExtraActions,
  MapComponent = CoverageMap,
  onSearchArea,
  sortFields = ["title", "dateStamp"],
}: {
  onSearchArea?: (geometry: string) => void;
  geometrySource?: string;
  showDetails?: boolean;
  namespace?: string;
  rowDetails?: (record: RaRecord) => ReactNode;
  rowActions?: (record: RaRecord) => ReactNode;
  /** Actions which belong next to show and edit instead of replacing them. */
  rowExtraActions?: (record: RaRecord) => ReactNode;
  MapComponent?: ComponentType<CoverageMapProps>;
  sortFields?: string[];
}) => {
  const { data = [], total, isPending } = useListContext();
  const translate = useTranslate();
  const [view, setView] = useState("split");
  const [selected, setSelected] = useState<Identifier>();
  const entries = useMemo(
    () =>
      data.flatMap((record) => {
        const bounds = getCoverageBounds(record[geometrySource]);
        return bounds ? [{ record, bounds }] : [];
      }),
    [data, geometrySource],
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
            {translate(`${namespace}.title`)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {translate(`${namespace}.count`, { count: total ?? 0 })}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <SortButton fields={sortFields} />
          <ToggleButtonGroup
            exclusive
            value={view}
            size="small"
            onChange={(_, value: string | null) => value && setView(value)}
            aria-label={translate(`${namespace}.view`)}
          >
            {["list", "split", "map"].map((mode) => (
              <ToggleButton key={mode} value={mode}>
                {translate(`${namespace}.${mode}`)}
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
            aria-label={translate(`${namespace}.results`)}
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
                              ? `${namespace}.hasCoverage`
                              : `${namespace}.missingCoverage`,
                          )}
                        />
                        <DateField source="dateStamp" />
                        {rowDetails?.(record)}
                      </Stack>
                    </Stack>
                  </ListItemButton>
                  <Stack
                    direction="row"
                    useFlexGap
                    sx={{ px: 1, pb: 1, flexWrap: "wrap", gap: 0.5 }}
                  >
                    {rowActions ? (
                      rowActions(record)
                    ) : (
                      <>
                        {showDetails && <ShowButton />}
                        <EditButton />
                        {rowExtraActions?.(record)}
                      </>
                    )}
                  </Stack>
                </ListItem>
                <Divider component="li" />
              </RecordContextProvider>
            ))}
          </List>
        )}
        {view !== "list" && (
          <MapComponent
            onSearchArea={
              onSearchArea
                ? (geometry) => {
                    setSelected(undefined);
                    onSearchArea(geometry);
                  }
                : undefined
            }
            showDetails={showDetails}
            namespace={namespace}
            entries={entries}
            selected={selected}
            onSelect={setSelected}
          />
        )}
      </Box>
    </Stack>
  );
};

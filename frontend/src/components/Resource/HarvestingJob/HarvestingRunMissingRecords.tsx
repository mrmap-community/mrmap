import { type ReactElement } from "react";
import {
  DateField,
  FunctionField,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Box, Chip, Stack, Typography } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import ListActions from "../../Lists/CustomListActions";
import ListTemporaryMdMetadataFile from "../TemporaryMdMetadataFile/ListTemporaryMdMetadataFile";

/**
 * The words of the collecting states, at the number the api answers each at
 * (`registry/enums/harvesting.py:CollectingStatenEnum`).
 */
const STATE_WORDS = ["duplicated", "new", "updated", "existing", "removed"];

/** The record of the relation row, named by the one relation which is set. */
const REFERENCE_BY_SOURCE: Record<string, string> = {
  datasetMetadataRecord: "DatasetMetadataRecord",
  serviceMetadataRecord: "ServiceMetadataRecord",
  applicationMetadataRecord: "ApplicationMetadataRecord",
};

export interface HarvestedRecordReferenceFieldProps {
  /** the label of the column, translated by the caller */
  label?: string;
}

/**
 * One column for the record a relation row made: the row names it by exactly
 * one of its three relations, so the column reads which one it is and links
 * to it - a row of a record which was never made reads its empty text (#1083).
 */
export const HarvestedRecordReferenceField = ({
  label = "harvestRun.collectedRecord",
}: HarvestedRecordReferenceFieldProps): ReactElement => {
  const record = useRecordContext();
  const chosen = Object.entries(REFERENCE_BY_SOURCE).find(
    ([source]) => record?.[source]?.id != null,
  );
  return (
    <JsonApiReferenceField
      source={chosen?.[0] ?? "datasetMetadataRecord"}
      reference={chosen?.[1] ?? "DatasetMetadataRecord"}
      label={label}
      emptyText="—"
    />
  );
};

/**
 * What a run did not store, both answers it gives about them in one tab:
 * the files whose import the catalogue's response refused, and what became
 * of the records it did read - which of them it found new, updated, already
 * there, duplicated or gone (#1083).
 */
const HarvestingRunMissingRecords = (): ReactElement | null => {
  const run = useRecordContext();
  const translate = useTranslate();
  if (!run) return null;
  const relatedResource = { resource: "HarvestingJob", id: run.id };
  const refetchInterval = run.doneAt ? false : 5000;
  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h6" sx={{ px: 2, pt: 1 }}>
          {translate("harvestRun.refusedByImport")}
        </Typography>
        <ListTemporaryMdMetadataFile
          relatedResource={relatedResource}
          refetchInterval={refetchInterval}
          storeKey={false}
        />
      </Box>
      <Box>
        <Typography variant="h6" sx={{ px: 2, pt: 1 }}>
          {translate("harvestRun.collectedStates")}
        </Typography>
        <ListGuesser
          resource="HarvestedMetadataRelation"
          relatedResource={relatedResource}
          sort={{ field: "historyDate", order: "DESC" }}
          storeKey={false}
          refetchInterval={refetchInterval}
          rowActions={<></>}
          ActionsComponent={(props) => (
            <ListActions
              {...props}
              isConfigureable={false}
              isExportable={false}
            />
          )}
          columns={[
            <FunctionField
              key="collectingState"
              source="collectingState"
              sortable={false}
              label="harvestRun.collectedState"
              render={(record) => {
                const word = STATE_WORDS[Number(record?.collectingState)];
                if (word === undefined) return null;
                return (
                  <Chip
                    size="small"
                    color={word === "duplicated" || word === "removed" ? "warning" : "default"}
                    label={translate(`harvestRun.collectingStates.${word}`)}
                  />
                );
              }}
            />,
            <HarvestedRecordReferenceField key="record" />,
            <DateField
              key="historyDate"
              source="historyDate"
              showTime
              label="harvestRun.collectedAt"
            />,
          ]}
        />
      </Box>
    </Stack>
  );
};

export default HarvestingRunMissingRecords;

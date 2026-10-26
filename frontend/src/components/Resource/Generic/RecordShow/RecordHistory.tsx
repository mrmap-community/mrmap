import { createElement, useMemo } from "react";
import {
  Datagrid,
  ReferenceField,
  ResourceContextProvider,
  TextField,
  useRecordContext,
  useResourceContext,
  useTranslate,
} from "react-admin";

import { Chip } from "@mui/material";

import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import HistoryList from "../History/HistoryList";
import { recordHistorySource } from "../History/historySources";
import { choiceLabel } from "./RecordFields";

const CollectingState = ({ source }: { source: string; label?: string }) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: "retrieve_HarvestedMetadataRelation",
    forInput: false,
  });
  const choices = fields.find((field) => field.props.source === source)?.props
    .choices;
  return (
    <Chip
      size="small"
      label={
        choiceLabel(record?.[source], choices) ??
        translate("recordShow.unknown")
      }
    />
  );
};

const HarvestCatalogue = ({ source }: { source: string; label?: string }) => (
  <ReferenceField
    source={`${source}.id`}
    reference="HarvestingJob"
    link={false}
  >
    <ReferenceField
      source="service.id"
      reference="CatalogueService"
      link="show"
    >
      <TextField source="stringRepresentation" />
    </ReferenceField>
  </ReferenceField>
);

const RecordHistory = ({ harvests = false }: { harvests?: boolean }) => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const fields = useFieldsForOperation({
    operationId: "retrieve_HarvestedMetadataRelation",
    forInput: false,
  });
  const sources = useMemo(
    () =>
      record && resource ? [recordHistorySource(resource, record.id)] : [],
    [resource, record?.id],
  );
  if (!record) return null;
  if (!harvests)
    return (
      <HistoryList
        variant="timeline"
        key={`${resource}:${record.id}`}
        sources={sources}
        record={record}
      />
    );
  return (
    <ResourceContextProvider value="HarvestedMetadataRelation">
      <ListGuesser
        resource="HarvestedMetadataRelation"
        filter={{
          [resource === "DatasetMetadataRecord"
            ? "dataset_metadata_record__id"
            : "service_metadata_record__id"]: record.id,
        }}
        listContent={
          <Datagrid bulkActionButtons={false} rowClick={false}>
            {fields
              .filter((field) =>
                [
                  "harvestingJob",
                  "collectingState",
                  "downloadDuration",
                  "processingDuration",
                  "historyDate",
                ].includes(field.props.source),
              )
              .map((field) =>
                createElement(
                  field.props.source === "collectingState"
                    ? CollectingState
                    : field.props.source.endsWith("Duration")
                      ? TextField
                      : field.component,
                  { ...field.props, key: field.props.source },
                ),
              )}
            <HarvestCatalogue
              source="harvestingJob"
              label="recordShow.catalogue"
            />
          </Datagrid>
        }
        sort={{ field: "historyDate", order: "DESC" }}
        disableSyncWithLocation
        storeKey={`${resource}.${record.id}.harvests`}
        actions={false}
        aside={undefined}
      />
    </ResourceContextProvider>
  );
};

export default RecordHistory;

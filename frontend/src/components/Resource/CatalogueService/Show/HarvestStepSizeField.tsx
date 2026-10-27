import { createElement } from "react";
import { type RaRecord, useResourceContext } from "react-admin";

import { Stack } from "@mui/material";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import HarvestThroughputHint from "./HarvestThroughputHint";

/** the attribute a catalogue keeps the size of its harvests with */
const STEP_SIZE = "maxStepSize";

interface StepSizeFieldProps {
  /** the attribute this field edits, named as the schema of the catalogue names it */
  source: string;
  /** the catalogue which is edited */
  record?: RaRecord;
  [key: string]: unknown;
}

/**
 * The size a harvest of the catalogue starts with, next to what its runs measured.
 *
 * The field itself is the one the schema of a catalogue answers, so its label,
 * its limits and its help text stay what the api says of the size - only the
 * measurement of this catalogue is added below it. The size is the memory of the
 * page size a remote catalogue answers, and a memory is only worth keeping as
 * long as the runs say it is still the fastest one (#692).
 */
const HarvestStepSizeField = ({
  source,
  record,
  ...input
}: StepSizeFieldProps) => {
  const resource = useResourceContext();
  const fields = useFieldsForOperation({
    operationId: `partial_update_${resource}`,
  });
  const field = fields.find(
    (definition) => definition.props.source === source,
  );
  if (!field) return null;
  const currentSize = record?.[STEP_SIZE];
  return (
    <Stack spacing={0.5}>
      {createElement(field.component, { ...input, record })}
      {record?.id != null && (
        <HarvestThroughputHint
          serviceId={record.id}
          currentSize={typeof currentSize === "number" ? currentSize : undefined}
        />
      )}
    </Stack>
  );
};

export default HarvestStepSizeField;

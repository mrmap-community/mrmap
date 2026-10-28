import { createElement, type ReactNode } from "react";
import { type RaRecord, useResourceContext } from "react-admin";

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
 * The field itself is the one the schema of a catalogue answers, so its label and
 * its limits stay what the api says of the size. The measurement joins the field as
 * the helper text of that very input, which is where the api's own description of
 * the size is read: one caption block below the input, in the typography and the
 * color a description of a field always has, instead of a second block of text of
 * its own next to it. The description stays first - the measurement qualifies the
 * value the api explains, it does not replace it. While the form has a validation
 * error to tell, react-admin answers that error in this slot instead of the
 * measurement, because an error outranks a hint.
 *
 * The size is the memory of the page size a remote catalogue answers, and a memory
 * is only worth keeping as long as the runs say it is still the fastest one (#692).
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
  const description = (input.helperText ?? field.props.helperText) as ReactNode;
  return createElement(field.component, {
    ...field.props,
    ...input,
    source,
    record,
    // a catalogue which is not saved yet has no runs which could have measured anything,
    // so the input answers its description alone
    helperText:
      record?.id == null ? (
        description
      ) : (
        <>
          {description}
          <HarvestThroughputHint
            serviceId={record.id}
            currentSize={
              typeof currentSize === "number" ? currentSize : undefined
            }
          />
        </>
      ),
  });
};

export default HarvestStepSizeField;

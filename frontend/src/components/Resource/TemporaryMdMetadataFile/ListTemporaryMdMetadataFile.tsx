import { type ReactElement } from "react";
import { DateField, TextField } from "react-admin";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { type RelatedResource } from "../../../providers/dataProvider";
import TruncatedTextField from "../../Field/TruncatedTextField";
import ListActions from "../../Lists/CustomListActions";

export interface ListTemporaryMdMetadataFileProps {
  /** the run whose refused files are listed, which is the parent of the nested route */
  relatedResource?: Partial<RelatedResource>;
  /** passed to the list: a running run keeps its page fresh, a closed one does not */
  refetchInterval?: number | false;
  /** passed to the list: a tab of a run does not persist its list parameters */
  storeKey?: string | false;
}

/**
 * The files a run downloaded but could not store, newest request first.
 *
 * The list is fixed to the files with an import error: their `importError`
 * says what the import refused, which is the question the run screen asks
 * (#1083). The columns are declared and the column chooser is off because
 * the remaining fields of the file - the response content behind
 * `mdMetadataFile` above all - are no columns, they are a read of the file
 * which this list must never start for every row (#888).
 */
const ListTemporaryMdMetadataFile = ({
  relatedResource,
  refetchInterval = false,
  storeKey,
}: ListTemporaryMdMetadataFileProps): ReactElement => (
  <ListGuesser
    resource="TemporaryMdMetadataFile"
    relatedResource={relatedResource}
    filter={{ hasImportError: true }}
    sort={{ field: "requestId", order: "DESC" }}
    storeKey={storeKey}
    refetchInterval={refetchInterval}
    rowActions={<></>}
    ActionsComponent={(props) => (
      <ListActions {...props} isConfigureable={false} isExportable={false} />
    )}
    columns={[
      <DateField
        key="requestId"
        source="requestId"
        showTime
        label="harvestRun.failing.request"
      />,
      <TruncatedTextField
        key="requestedUrl"
        source="requestedUrl"
        label="harvestRun.failing.page"
      />,
      <TruncatedTextField
        key="importError"
        source="importError"
        label="harvestRun.failing.refusedWith"
      />,
      <TextField
        key="downloadDuration"
        source="downloadDuration"
        label="harvestRun.failing.downloadDuration"
      />,
    ]}
  />
);

export default ListTemporaryMdMetadataFile;

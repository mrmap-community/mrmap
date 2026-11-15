import {
  DeleteButton,
  useGetRecordRepresentation,
  useNotify,
  useRecordContext,
  useResourceContext,
  useResourceDefinition,
  useTranslate,
} from "react-admin";
import { Link } from "react-router-dom";

import {
  Button,
  Chip,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import RecordFields, { choiceLabel } from "./RecordFields";

const RecordHeader = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const representation = useGetRecordRepresentation(resource);
  const translate = useTranslate();
  const notify = useNotify();
  const { hasEdit, options } = useResourceDefinition();
  const fields = useFieldsForOperation({
    operationId: `retrieve_${resource}`,
    forInput: false,
  });
  if (!record) return null;
  const origin = choiceLabel(
    record.origin,
    fields.find((field) => field.props.source === "origin")?.props.choices,
  );
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      notify("recordShow.copied", { type: "info" });
    } catch {
      notify("recordShow.copyFailed", { type: "warning" });
    }
  };
  return (
    <Stack spacing={1} sx={{ p: 2, overflowWrap: "anywhere" }}>
      <Typography variant="h5">{representation(record)}</Typography>
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
        {origin && <Chip size="small" label={origin} />}
        <Chip
          size="small"
          label={translate(
            record.isSearchable
              ? "recordShow.searchable"
              : "recordShow.unpublished",
          )}
        />
        {record.isCustomized && (
          <Chip size="small" label={translate("recordShow.editorSaved")} />
        )}
        {record.isBroken && (
          <Tooltip
            title={
              record.insufficientQuality || translate("recordShow.unknown")
            }
          >
            <Chip
              tabIndex={0}
              color="error"
              size="small"
              label={translate("recordShow.broken")}
            />
          </Tooltip>
        )}
        {record.licence?.isOpenData && (
          <Chip
            size="small"
            color="success"
            label={translate("recordShow.openData")}
          />
        )}
      </Stack>
      <RecordFields
        sources={["createdAt", "createdBy", "lastModifiedAt", "lastModifiedBy"]}
      />
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
        {hasEdit && record.canEdit && (
          <Button component={Link} to={`/metadata/${resource}/${record.id}/edit`}>
            {translate("ra.action.edit")}
          </Button>
        )}
        {options?.hasDelete && record.canDelete && <DeleteButton />}
        <Button onClick={() => void copy(String(record.id))}>
          {translate("recordShow.copyId")}
        </Button>
        {record.resourceIdentifier && (
          <Button onClick={() => void copy(record.resourceIdentifier)}>
            {translate("recordShow.copyIdentifier")}
          </Button>
        )}
        {record.originUrl && (
          <Button
            href={record.originUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            {translate("recordShow.source")}
          </Button>
        )}
      </Stack>
    </Stack>
  );
};

export default RecordHeader;

import { useState } from "react";
import {
  DeleteButton,
  useGetRecordRepresentation,
  useNotify,
  useRecordContext,
  useResourceContext,
  useResourceDefinition,
  useShowContext,
  useTranslate,
  Toolbar,
  SaveButton,
} from "react-admin";

import {
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";

import EditGuesser from "../../../../jsonapi/components/EditGuesser";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import RecordFields, { choiceLabel } from "./RecordFields";

const RecordHeader = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const representation = useGetRecordRepresentation(resource);
  const translate = useTranslate();
  const notify = useNotify();
  const { hasEdit, options } = useResourceDefinition();
  const { refetch } = useShowContext();
  const [editing, setEditing] = useState(false);
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
          <Chip size="small" label={translate("recordShow.writtenAgain")} />
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
          <Button onClick={() => setEditing(true)}>
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
      <Dialog
        open={editing}
        onClose={() => setEditing(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {translate("ra.action.edit")}{" "}
          <Button onClick={() => setEditing(false)}>
            {translate("ra.action.close")}
          </Button>
        </DialogTitle>
        <DialogContent>
          {editing && (
            <EditGuesser
              id={record.id}
              resource={resource}
              redirect={false}
              actions={false}
              simpleFormProps={{
                toolbar: (
                  <Toolbar>
                    <SaveButton />
                  </Toolbar>
                ),
              }}
              mutationOptions={{
                onSuccess: () => {
                  setEditing(false);
                  void refetch();
                  notify("ra.notification.updated", {
                    type: "info",
                    messageArgs: { smart_count: 1 },
                  });
                },
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Stack>
  );
};

export default RecordHeader;

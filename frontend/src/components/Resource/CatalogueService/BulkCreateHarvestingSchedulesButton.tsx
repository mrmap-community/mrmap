import { useId, useState } from "react";
import {
  Button,
  type Identifier,
  ResourceContextProvider,
  SimpleForm,
  useCreate,
  useGetIdentity,
  useListContext,
  useNotify,
  useRefresh,
  useResourceDefinition,
  useTranslate,
  useUnselect,
} from "react-admin";

import UpdateIcon from "@mui/icons-material/Update";
import { Alert, Box, LinearProgress, Stack, Typography } from "@mui/material";

import SchemaAutocompleteInput from "../../../jsonapi/components/SchemaAutocompleteInput";
import SchemaFormFields from "../../../jsonapi/components/SchemaFormFields";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import Dialog from "../../Dialog/Dialog";
import DialogHeader from "../../Dialog/DialogHeader";
import CronInput from "../../Input/CronInput";

// CreateDialogButton creates one resource; this workflow shares its dialog and
// schema fields while submitting one schedule for each selected catalogue.
const BulkCreateHarvestingSchedulesButton = () => {
  const { selectedIds = [] } = useListContext();
  const { hasCreate } = useResourceDefinition({ resource: "PeriodicHarvestingJob" });
  const { data: identity } = useGetIdentity();
  const fields = useFieldsForOperation({ operationId: "create_PeriodicHarvestingJob" });
  const source = fields.find(field =>
    field.component === SchemaAutocompleteInput &&
    field.props.reference === "CatalogueService" && !field.props.multiple,
  )?.props.source;
  const [create] = useCreate();
  const unselect = useUnselect("CatalogueService");
  const notify = useNotify();
  const refresh = useRefresh();
  const translate = useTranslate();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [serviceIds, setServiceIds] = useState<Identifier[]>([]);
  const [failures, setFailures] = useState<Identifier[]>([]);
  const [saving, setSaving] = useState(false);

  const close = () => { if (!saving) setOpen(false); };
  const submit = async (values: Record<string, unknown>) => {
    if (!source || saving) return;
    setSaving(true);
    const succeeded: Identifier[] = [];
    const failed: Identifier[] = [];
    for (const id of serviceIds) {
      try {
        await create(
          "PeriodicHarvestingJob",
          { data: { ...values, [source]: { id } } },
          { returnPromise: true },
        );
        succeeded.push(id);
      } catch {
        failed.push(id);
      }
    }
    setSaving(false);
    unselect(succeeded);
    refresh();
    notify("harvestingSchedules.bulkResult", {
      type: failed.length ? "warning" : "success",
      messageArgs: { created: succeeded.length, failed: failed.length },
    });
    setFailures(failed);
    setServiceIds(failed);
    if (!failed.length) setOpen(false);
  };

  if (!hasCreate || !identity?.id || !source) return null;
  return (
    <>
      <Button
        label="harvestingSchedules.bulkCreate"
        startIcon={<UpdateIcon />}
        disabled={!selectedIds.length}
        onClick={() => {
          setServiceIds([...selectedIds]);
          setFailures([]);
          setOpen(true);
        }}
      />
      {open && (
        <ResourceContextProvider value="PeriodicHarvestingJob">
          <SimpleForm id={formId} onSubmit={submit} toolbar={false}>
            <Dialog
              open
              onClose={close}
              maxWidth="sm"
              title={<DialogHeader onClose={close}>{translate("harvestingSchedules.bulkCreate")}</DialogHeader>}
              actions={<>
                <Button label="ra.action.cancel" onClick={close} disabled={saving} />
                <Button
                  label="harvestingSchedules.bulkCreate"
                  type="submit"
                  form={formId}
                  variant="contained"
                  disabled={saving}
                  startIcon={<UpdateIcon />}
                />
              </>}
            >
              <Stack spacing={2}>
                <Typography>{translate("harvestingSchedules.bulkDescription", { smart_count: serviceIds.length })}</Typography>
                {!!failures.length && (
                  <Alert severity="error">{translate("harvestingSchedules.bulkFailed", { ids: failures.join(", ") })}</Alert>
                )}
                {saving && <LinearProgress />}
                <Box component="fieldset" disabled={saving} sx={{ border: 0, p: 0, m: 0 }}>
                  <SchemaFormFields
                    operationId="create_PeriodicHarvestingJob"
                    omit={[source]}
                    overrides={[{ component: CronInput, props: { source: "scheduling" } }]}
                  />
                </Box>
              </Stack>
            </Dialog>
          </SimpleForm>
        </ResourceContextProvider>
      )}
    </>
  );
};

export default BulkCreateHarvestingSchedulesButton;

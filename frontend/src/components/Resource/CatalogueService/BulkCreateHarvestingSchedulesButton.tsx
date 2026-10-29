import { useId, useState } from "react";
import {
  Button,
  type Identifier,
  ResourceContextProvider,
  SimpleForm,
  useCreate,
  useGetIdentity,
  useGetMany,
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
  const services = useGetMany(
    "CatalogueService",
    { ids: serviceIds, meta: { jsonApiParams: { "fields[CatalogueService]": "id,is_harvestable" } } },
    { enabled: open && serviceIds.length > 0, refetchOnMount: "always", retry: false },
  );
  const ready = !services.isPending && !services.error && services.data?.length === serviceIds.length;
  const harvestableIds = services.data?.filter(service => service.isHarvestable === true).map(service => service.id) ?? [];
  const excludedIds = serviceIds.filter(id => !harvestableIds.includes(id));

  const close = () => { if (!saving) setOpen(false); };
  const submit = async (values: Record<string, unknown>) => {
    if (!source || saving || !ready || !harvestableIds.length) return;
    setSaving(true);
    const succeeded: Identifier[] = [];
    const failed: Identifier[] = [];
    for (const id of harvestableIds) {
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
    unselect([...succeeded, ...excludedIds]);
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
                  disabled={saving || !ready || !harvestableIds.length}
                  startIcon={<UpdateIcon />}
                />
              </>}
            >
              <Stack spacing={2}>
                <Typography>{translate("harvestingSchedules.bulkDescription", { smart_count: harvestableIds.length })}</Typography>
                {services.isPending && <LinearProgress />}
                {!services.isPending && !ready && <Alert severity="error">{translate("harvestingSchedules.bulkLoadError")}</Alert>}
                {ready && excludedIds.length > 0 && <Alert severity="info">{translate("harvestingSchedules.unavailable")}</Alert>}
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

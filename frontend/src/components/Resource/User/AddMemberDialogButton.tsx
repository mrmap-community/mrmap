import { useId, useState } from "react";
import {
  Button,
  ResourceContextProvider,
  SimpleForm,
  useCreate,
  useNotify,
  useRefresh,
  useTranslate,
} from "react-admin";

import PersonAddIcon from "@mui/icons-material/PersonAdd";
import { LinearProgress } from "@mui/material";

import SchemaAutocompleteInput from "../../../jsonapi/components/SchemaAutocompleteInput";
import ContextBasedDialog from "../../Dialog/Dialog";
import DialogHeader from "../../Dialog/DialogHeader";
import { useOrganizationScope } from "../Generic/Administration/OrganizationScopeContext";

/**
 * The "add member" control of the #737 Members screen. It reuses the shared
 * dialog and the `ResourceRelatedField`-backed user search (the way the
 * keyword fields search) and submits the resource-identifier payload
 * `POST /organizations/{id}/members` asks for (#736: the document is the
 * user's resource identifier, its `id` names the user to add; adding grants
 * no role - that stays the separate step beside `/roles/{id}/memberships`).
 */
export const AddMemberDialogButton = () => {
  const translate = useTranslate();
  const { organizationId, canAdminister } = useOrganizationScope();
  const [create] = useCreate();
  const notify = useNotify();
  const refresh = useRefresh();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  if (organizationId === undefined || !canAdminister) {
    return null;
  }

  const close = () => {
    if (!saving) {
      setOpen(false);
    }
  };

  const submit = async (values: Record<string, unknown>) => {
    const chosen = values.user as { id?: string, stringRepresentation?: unknown } | string | undefined;
    const userId = typeof chosen === "object" ? chosen?.id : chosen;
    // the notification names the user by the representation the search
    // answer carries; anything but a string falls back to the id rather
    // than reading "[object Object]" in a sentence
    const userLabel = typeof chosen === "object"
      ? (typeof chosen.stringRepresentation === "string"
        ? chosen.stringRepresentation
        : String(userId))
      : String(chosen);
    if (userId === undefined || userId === "" || saving) {
      return;
    }
    setSaving(true);
    try {
      await create(
        "User",
        {
          data: { id: String(userId) },
          meta: { relatedResource: { resource: "Organization", id: organizationId } },
        },
        { returnPromise: true },
      );
      notify("administration.members.added", {
        type: "success",
        messageArgs: { user: userLabel },
      });
      refresh();
      setOpen(false);
    } catch {
      // the backend answers who may add members and who is already one; its
      // error stays the last word, the dialog just reports that it failed
      notify("administration.members.addFailed", { type: "error" });
    }
    setSaving(false);
  };

  return (
    <>
      <Button
        label="administration.members.add"
        startIcon={<PersonAddIcon />}
        onClick={() => setOpen(true)}
      />
      {open && (
        <ResourceContextProvider value="User">
          <SimpleForm id={formId} onSubmit={submit} toolbar={false}>
            <ContextBasedDialog
              open
              onClose={close}
              maxWidth="sm"
              title={<DialogHeader onClose={close}>{translate("administration.members.addTitle")}</DialogHeader>}
              actions={<>
                <Button label="ra.action.cancel" onClick={close} disabled={saving} />
                <Button
                  label="administration.members.add"
                  type="submit"
                  form={formId}
                  variant="contained"
                  disabled={saving}
                  startIcon={<PersonAddIcon />}
                />
              </>}
              actionsAlign="flex-end"
            >
              {saving && <LinearProgress />}
              <SchemaAutocompleteInput
                reference="User"
                source="user"
                label={translate("administration.members.user")}
              />
            </ContextBasedDialog>
          </SimpleForm>
        </ResourceContextProvider>
      )}
    </>
  );
};

export default AddMemberDialogButton;

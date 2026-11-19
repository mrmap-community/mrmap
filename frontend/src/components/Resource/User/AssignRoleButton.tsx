import { useId, useState } from "react";
import {
  Button,
  ResourceContextProvider,
  SelectInput,
  SimpleForm,
  useCreate,
  useNotify,
  useRecordContext,
  useTranslate,
} from "react-admin";

import PersonIcon from "@mui/icons-material/PersonAddAlt";
import { LinearProgress } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";

import ContextBasedDialog from "../../Dialog/Dialog";
import DialogHeader from "../../Dialog/DialogHeader";
import { useOrganizationScope } from "../Generic/Administration/OrganizationScopeContext";

/**
 * The row-level "assign role" control of the #737 Members screen. Assigning
 * is the POST against the chosen organization role's membership collection
 * (`create_related_RoleMembership_of_Role`); the serializer of #736 decides
 * what the payload may say - the member must belong to the role's own
 * organization, and the authority to assign answers 403 before anything
 * about a legal payload is disclosed. The offer list is the organization's
 * role rows the member does not hold yet.
 */
export const AssignRoleButton = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const { roles, canAdminister } = useOrganizationScope();
  const [create] = useCreate();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const heldIds = new Set<string>(
    (Array.isArray(record?.roles) ? record.roles as { id: string }[] : [])
      .map(held => String(held.id))
  );
  const choices = roles
    .filter(role => !heldIds.has(role.id))
    .map(role => ({ id: role.id, name: role.label !== "" ? role.label : role.slug }));

  if (record === undefined || !canAdminister || choices.length === 0) {
    return null;
  }

  const close = () => {
    if (!saving) {
      setOpen(false);
    }
  };

  const submit = async (values: Record<string, unknown>) => {
    const roleId = values.role as string | undefined;
    if (roleId === undefined || saving) {
      return;
    }
    setSaving(true);
    try {
      await create(
        "RoleMembership",
        {
          data: { role: { id: roleId }, user: { id: String(record.id) } },
          meta: { relatedResource: { resource: "Role", id: roleId } },
        },
        { returnPromise: true },
      );
      const assigned = roles.find(role => role.id === roleId);
      notify("administration.members.assigned", {
        type: "success",
        messageArgs: { role: assigned?.slug ?? roleId },
      });
      // the chip row of the member reads the roles the members list answers
      // per row; only that collection has to be re-read, not everything
      queryClient.invalidateQueries({ queryKey: ["User", "getList"] });
      setOpen(false);
    } catch {
      notify("administration.members.assignFailed", { type: "error" });
    }
    setSaving(false);
  };

  return (
    <>
      <Button
        label="administration.members.assign"
        onClick={() => setOpen(true)}
      >
        <PersonIcon />
      </Button>
      {open && (
        <ResourceContextProvider value="RoleMembership">
          <SimpleForm id={formId} onSubmit={submit} toolbar={false}>
            <ContextBasedDialog
              open
              onClose={close}
              maxWidth="sm"
              title={<DialogHeader onClose={close}>
                {translate("administration.members.assignTitle", {
                  user: String(record.username ?? record.id),
                })}
              </DialogHeader>}
              actions={<>
                <Button label="ra.action.cancel" onClick={close} disabled={saving} />
                <Button
                  label="administration.members.assign"
                  type="submit"
                  form={formId}
                  variant="contained"
                  disabled={saving}
                />
              </>}
              actionsAlign="flex-end"
            >
              {saving && <LinearProgress />}
              <SelectInput
                source="role"
                label={translate("administration.members.role")}
                choices={choices}
                optionText="name"
                optionValue="id"
              />
            </ContextBasedDialog>
          </SimpleForm>
        </ResourceContextProvider>
      )}
    </>
  );
};

export default AssignRoleButton;

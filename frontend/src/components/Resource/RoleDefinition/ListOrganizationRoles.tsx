import { createElement, useMemo, type ReactElement } from "react";
import { FunctionField, useTranslate } from "react-admin";

import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import useResourceSchema from "../../../jsonapi/hooks/useResourceSchema";
import { FieldDefinition, getIncludeOptions } from "../../../jsonapi/utils";
import {
  OrganizationScopeProvider,
  useOrganizationScope,
} from "../Generic/Administration/OrganizationScopeContext";
import OrganizationScopeSelect from "../Generic/Administration/OrganizationScopeSelect";

/**
 * The `verb_model` reading of a Django permission codename - `view_user` is
 * the `view` on `user`. The Django app label a permission belongs to is not
 * answered by any endpoint (`Permission.content_type` stays a relationship id
 * of a row no API exposes), so the grouping of the issue's "per app and
 * model" reads as far as the API lets it: per model.
 */
const parseCodename = (codename: string): { action: string, model: string } => {
  const separator = codename.indexOf("_");
  return separator === -1
    ? { action: codename, model: "" }
    : { action: codename.slice(0, separator), model: codename.slice(separator + 1) };
};

/**
 * The permissions of one definition, grouped per model. The codenames come
 * with the list when its schema declares `permissions` in the `include`
 * enum (the include of #735's serializer wiring); without that answer the
 * cell says how many permissions the definition holds - ids of permission
 * rows carry nothing to render, and the count is the honest remainder.
 */
const RolePermissionsCell = ({ record }: { record?: Record<string, unknown> }) => {
  const translate = useTranslate();
  const permissions = Array.isArray(record?.permissions)
    ? record.permissions as { id?: string, codename?: string }[]
    : [];
  const known = permissions.filter(permission =>
    typeof permission.codename === "string");
  if (known.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("administration.roles.permissionCount", { smart_count: permissions.length })}
      </Typography>
    );
  }
  const perModel = new Map<string, string[]>();
  known.forEach(permission => {
    const { action, model } = parseCodename(permission.codename as string);
    perModel.set(model, [...(perModel.get(model) ?? []), action]);
  });
  return (
    <Stack spacing={0.5}>
      {[...perModel.entries()].map(([model, actions]) => (
        <Stack key={model || "permissions"} direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
          {model !== "" && (
            <Typography variant="body2" component="span">
              {model}
            </Typography>
          )}
          {actions.map(action => (
            <Chip key={`${model}:${action}`} size="small" label={action}/>
          ))}
        </Stack>
      ))}
    </Stack>
  );
};

const RolesList = (): ReactElement => {
  const translate = useTranslate();
  const { organizationId, roles } = useOrganizationScope();
  const { operation } = useResourceSchema("list_RoleDefinition");
  // an include the operation's schema does not name is a request the backend
  // would answer 400 - the enum is the contract (jsonapi/AGENTS.md)
  const includePermissions = operation !== undefined
    && getIncludeOptions(operation).includes("permissions");
  const fields = useFieldsForOperation({
    operationId: "list_RoleDefinition",
    forInput: false,
    ignoreId: false,
  });
  const columns = useMemo(() => {
    const schemaColumns = ["slug", "label", "description"]
      .map(source => fields.find(field => field.props.source === source))
      .filter((field): field is FieldDefinition => field !== undefined)
      .map(field =>
        createElement(field.component, { ...field.props, key: field.props.source }));
    return [
      ...schemaColumns,
      <FunctionField
        key="memberCount"
        label={translate("administration.roles.members")}
        render={(record: Record<string, unknown>) => organizationId === undefined
          ? null
          : String(roles.find(role => role.definitionId === String(record.id))?.memberCount ?? 0)}
      />,
      <FunctionField
        key="permissions"
        label={translate("administration.roles.permissions")}
        render={(record: Record<string, unknown>) =>
          <RolePermissionsCell record={record}/>}
      />,
    ];
  }, [fields, organizationId, roles, translate]);

  return (
    <ListGuesser
      resource="RoleDefinition"
      sort={{ field: "slug", order: "ASC" }}
      header={<OrganizationScopeSelect />}
      columns={columns}
      {...(includePermissions
        ? { queryOptions: { meta: { jsonApiParams: { include: "permissions" } } } }
        : {})}
    />
  );
};

/**
 * The Roles screen of the #737 administration area - the catalogue of
 * definitions (`RoleDefinition`, readable by every account, editable as a
 * platform act) annotated with the selected organization: how many members
 * hold each definition there, answered by the organization's role rows of
 * #736. Editing stays the schema-driven edit the resource offers; the server
 * decides who may save what (#736: writes to the catalogue are platform
 * acts), so an organization administrator's attempt fails as a notification,
 * never as a silently different frontend model.
 */
const ListOrganizationRoles = (): ReactElement => (
  <OrganizationScopeProvider>
    <RolesList />
  </OrganizationScopeProvider>
);

export default ListOrganizationRoles;

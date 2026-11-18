import { createElement, Fragment, useMemo, type ReactElement } from "react";
import { useTranslate, WrapperField } from "react-admin";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import { FieldDefinition } from "../../../jsonapi/utils";
import CustomListActions, {
  CustomListActionsProps,
} from "../../Lists/CustomListActions";
import {
  OrganizationScopeProvider,
  useOrganizationScope,
} from "../Generic/Administration/OrganizationScopeContext";
import OrganizationScopeSelect from "../Generic/Administration/OrganizationScopeSelect";
import HistoryChangelogLink from "../Generic/History/HistoryChangelogLink";
import AddMemberDialogButton from "./AddMemberDialogButton";
import AssignRoleButton from "./AssignRoleButton";
import MemberRolesCell from "./MemberRolesCell";

/**
 * The toolbar of the Members screen: the columns and filters machinery of
 * `ListGuesser` plus the "add member" control - and no plain "create user"
 * button, because adding a member links an existing user to the organization,
 * which is the dialog's job, not a `create_User`.
 */
const MembersActions = ({ preferenceKey }: CustomListActionsProps) => {
  const { canAdminister } = useOrganizationScope();
  return (
    <CustomListActions
      preferenceKey={preferenceKey}
      createButton={false}
      isExportable={false}
      additionalActions={(
        <Fragment>
          {canAdminister ? <AddMemberDialogButton /> : null}
          {/* who was granted which role, by whom and who took it back again -
              the changelog of the memberships, which #741 keeps beside the
              rows themselves and which every account may read at least for
              its own grants, so the link is not an administrator's tool */}
          <HistoryChangelogLink
            resource="RoleMembership"
            label="administration.audit.memberships"
          />
        </Fragment>
      )}
    />
  );
};

const MembersList = (): ReactElement => {
  const translate = useTranslate();
  const { organizationId } = useOrganizationScope();
  const fields = useFieldsForOperation({
    operationId: "list_related_User_of_Organization",
    forInput: false,
    ignoreId: false,
  });
  // the members answer is the User resource scoped by the organization; its
  // grid names the columns explicitly because the roles of a member are not
  // the plain relationship field - they are the chips with their revoke
  const columns = useMemo(() => {
    const schemaColumns = ["username", "stringRepresentation"]
      .map(source => fields.find(field => field.props.source === source))
      .filter((field): field is FieldDefinition => field !== undefined)
      .map(field =>
        createElement(field.component, { ...field.props, key: field.props.source }));
    return [
      ...schemaColumns,
      <MemberRolesCell
        key="roles"
        source="roles"
        label={translate("administration.members.roles")}
      />,
    ];
  }, [fields, translate]);

  return (
    <ListGuesser
      resource="User"
      relatedResource={{ resource: "Organization", id: organizationId }}
      sort={{ field: "username", order: "ASC" }}
      header={<OrganizationScopeSelect />}
      actions={<MembersActions />}
      columns={columns}
      rowActions={
        <WrapperField label={translate("ra.list.actions")}>
          <AssignRoleButton />
        </WrapperField>
      }
    />
  );
};

/**
 * The Members screen of the #737 administration area - the `list` of the
 * User resource, scoped to the organization selected in the shared scope
 * (the nested collection `/organizations/{id}/members`, which answers each
 * member with their roles in that organization). The screen is gated as a
 * whole by #836's `canAccess` over the User resource; inside it, organization
 * administrators see the organizations they administrate, platform holders
 * can switch between all of them.
 */
const ListOrganizationMembers = (): ReactElement => (
  <OrganizationScopeProvider>
    <MembersList />
  </OrganizationScopeProvider>
);

export default ListOrganizationMembers;

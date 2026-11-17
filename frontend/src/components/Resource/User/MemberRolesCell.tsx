import {
  useDataProvider,
  useGetIdentity,
  useNotify,
  useRecordContext,
  useRefresh,
  useTranslate,
} from "react-admin";
import { useNavigate } from "react-router-dom";

import CloseIcon from "@mui/icons-material/Close";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";

import { getPermissionSnapshot } from "../../../providers/authProvider";
import {
  hasAdministration,
  ORGANIZATION_ADMINISTRATION_ROLE,
} from "../../../providers/permissions";
import { useOrganizationScope } from "../Generic/Administration/OrganizationScopeContext";

/**
 * The role chips of one member row of the #737 Members screen. The roles a
 * member row carries are the ones this organization granted
 * (`OrganizationMemberSerializer.get_roles` scopes them); a chip revokes
 * through DELETE of the membership row of exactly this user and role.
 *
 * Revoking the caller's own administration role refreshes the permission
 * snapshot and react-admin's cached access answers immediately (the binding
 * Q9=B of #727): the menu follows without a reload, and when the caller held
 * no administration at all afterwards, the screen that no longer belongs to
 * them is left behind instead of standing there as a broken table.
 */
const MemberRolesCell = (_props: { source?: string, label?: string }) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const refresh = useRefresh();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: identity } = useGetIdentity();
  const { roles, canAdminister, reloadSnapshot } = useOrganizationScope();

  const roleLabel = (role: { slug: string, id: string }) =>
    role.slug !== "" ? role.slug : role.id;

  const revoke = async (roleId: string, slug: string) => {
    try {
      // the membership row is addressed by its two sides - both filters are
      // declared on `/memberships` (`RoleMembershipViewSetMixin`)
      const { data: memberships } = await dataProvider.getList("RoleMembership", {
        pagination: { page: 1, perPage: 1 },
        sort: { field: "id", order: "ASC" },
        filter: { role: roleId, user: String(record?.id) },
      });
      const membership = memberships[0];
      if (membership === undefined) {
        throw new Error("membership not found");
      }
      await dataProvider.delete("RoleMembership", { id: membership.id });

      const self = String(record?.id) === String(identity?.id ?? "");
      if (self && slug === ORGANIZATION_ADMINISTRATION_ROLE) {
        reloadSnapshot();
        // react-admin caches every canAccess answer per (resource, action);
        // the menu re-runs its checks against the snapshot being re-fetched
        queryClient.invalidateQueries({ queryKey: ["canAccess"] });
        const fresh = await getPermissionSnapshot();
        if (fresh !== undefined && !hasAdministration(fresh)) {
          notify("administration.members.selfRevoked", { type: "warning" });
          navigate("/");
          return;
        }
      }
      notify("administration.members.revoked", {
        type: "success",
        messageArgs: { role: slug !== "" ? slug : membership.id },
      });
      refresh();
    } catch {
      notify("administration.members.revokeFailed", { type: "error" });
    }
  };

  const held: { id: string }[] = Array.isArray(record?.roles)
    ? record.roles as { id: string }[]
    : [];

  if (held.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("administration.members.noRoles")}
      </Typography>
    );
  }

  return (
    <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.5 }}>
      {held.map(heldRole => {
        const role = roles.find(candidate => candidate.id === String(heldRole.id));
        const slug = role?.slug ?? "";
        const label = role !== undefined ? roleLabel(role) : String(heldRole.id);
        return (
          <Tooltip
            key={String(heldRole.id)}
            title={canAdminister
              ? translate("administration.members.revoke", { role: label })
              : undefined}
          >
            <Chip
              size="small"
              label={label}
              onDelete={canAdminister
                ? () => { void revoke(String(heldRole.id), slug); }
                : undefined}
              deleteIcon={<CloseIcon />}
            />
          </Tooltip>
        );
      })}
    </Stack>
  );
};

export default MemberRolesCell;

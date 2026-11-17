import type { ReactElement } from "react";
import { useTranslate, type RaRecord } from "react-admin";

import Autocomplete from "@mui/material/Autocomplete";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { useOrganizationScope } from "./OrganizationScopeContext";

const organizationLabel = (organization: RaRecord): string =>
  (organization.stringRepresentation as string | undefined)
  ?? (organization.name as string | undefined)
  ?? String(organization.id);

/**
 * The organization picker of both #737 administration screens. It renders the
 * options `useOrganizationScope` made visible for the caller and keeps its
 * choice in that shared scope, so Members and Roles show the same
 * organization without a global "active organization" state (#727 Q3: no
 * active-organization switch - the choice belongs to the administration
 * area, not to the session).
 */
export const OrganizationScopeSelect = (): ReactElement => {
  const translate = useTranslate();
  const {
    organizations,
    loadingOrganizations,
    organizationId,
    setOrganizationId,
  } = useOrganizationScope();

  const selected = organizations.find(
    organization => String(organization.id) === organizationId
  );

  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ p: 1, flexWrap: "wrap", alignItems: "center" }}
    >
      <Typography variant="subtitle2">
        {translate("administration.organization.label")}
      </Typography>
      <Autocomplete
        options={organizations}
        value={selected ?? null}
        onChange={(_event, chosen) =>
          setOrganizationId(chosen === null ? undefined : String(chosen.id))}
        getOptionLabel={organizationLabel}
        isOptionEqualToValue={(option, value) =>
          String(option.id) === String(value.id)}
        size="small"
        loading={loadingOrganizations}
        disabled={loadingOrganizations}
        sx={{ width: 320 }}
        renderInput={params => (
          <TextField
            {...params}
            label={translate("administration.organization.placeholder")}
          />
        )}
      />
      {!loadingOrganizations && organizations.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          {translate("administration.organization.noneForUser")}
        </Typography>
      )}
    </Stack>
  );
};

export default OrganizationScopeSelect;

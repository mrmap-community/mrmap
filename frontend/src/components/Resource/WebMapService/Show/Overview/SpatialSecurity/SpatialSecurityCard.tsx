import { Alert, Button, Chip, Stack, Tooltip, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import {
  Loading,
  type RaRecord,
  useBasename,
  useRecordContext,
  useTranslate,
} from "react-admin";
import SimpleCard from "../../../../../MUI/SimpleCard";
import useCompleteList from "./useCompleteList";

const SpatialSecuritySummary = () => {
  const service = useRecordContext();
  const translate = useTranslate();
  const basename = useBasename();
  const rules = useCompleteList("AllowedWebMapServiceOperation", service?.id);
  const message = (key: string) => translate(`spatialSecurity.${key}`);
  const spatialRules = rules.records.filter((rule) => rule.allowedArea != null);
  const countRelated = (source: string) =>
    new Set(
      spatialRules.flatMap((rule) =>
        rule[source].map((item: RaRecord) => String(item.id)),
      ),
    ).size;
  const pending =
    rules.isPending || rules.hasNextPage || rules.isFetchingNextPage;
  const unrestrictedRules = rules.records.length - spatialRules.length;
  return (
    <SimpleCard
      title={
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}
        >
          <Typography variant="h6" component="span">
            {message("title")}
          </Typography>
          {!rules.error && !pending && (
            <Chip
              size="small"
              color="info"
              variant="outlined"
              label={message(
                rules.records.length === 0
                  ? "notConfigured"
                  : spatialRules.length === 0
                    ? "noSpatialRestrictions"
                    : "configured",
              )}
            />
          )}
        </Stack>
      }
      headerProps={{
        sx: {
          py: 1.5,
          "& .MuiCardHeader-action": { alignSelf: "center", m: 0 },
        },
        action: (
          <Button
            component={Link}
            to={`${basename}/AllowedWebMapServiceOperation`}
          >
            {message("testPolicies")}
          </Button>
        ),
      }}
      contentProps={{ sx: { py: 1.5, "&:last-child": { pb: 1.5 } } }}
      divider={false}
      cardProps={{ sx: { width: "100%", border: 1, borderColor: "info.main" } }}
    >
      {rules.error ? (
        <Alert
          severity="error"
          action={
            <Button onClick={() => void rules.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {message("loadError")}
        </Alert>
      ) : pending ? (
        <Loading />
      ) : (
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            {[
              [spatialRules.length, "spatialRuleCount", "spatialRuleHint"],
              [countRelated("securedLayers"), "layerCount", "layerHint"],
              [countRelated("allowedGroups"), "groupCount", "groupHint"],
            ].map(([count, label, hint]) => (
              <Tooltip key={label} title={message(String(hint))}>
                <Stack
                  direction="row"
                  spacing={1}
                  tabIndex={0}
                  sx={{ flex: 1, alignItems: "baseline", width: "fit-content" }}
                >
                  <Typography variant="h5">{count}</Typography>
                  <Typography color="text.secondary">
                    {message(String(label))}
                  </Typography>
                </Stack>
              </Tooltip>
            ))}
          </Stack>
          {spatialRules.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {message(
                rules.records.length === 0 ? "noRules" : "noSpatialRules",
              )}
            </Typography>
          )}
          {spatialRules.some((rule) => rule.allowedGroups.length === 0) && (
            <Typography variant="body2">{message("allGroups")}</Typography>
          )}
          {unrestrictedRules > 0 && (
            <Alert severity="warning">
              {translate("spatialSecurity.unrestrictedRules", {
                count: unrestrictedRules,
              })}
            </Alert>
          )}
          <Typography variant="body2" color="text.secondary">
            {message("summaryNote")}
          </Typography>
        </Stack>
      )}
    </SimpleCard>
  );
};

const SpatialSecurityCard = () => {
  const service = useRecordContext();
  return service ? <SpatialSecuritySummary key={service.id} /> : null;
};

export default SpatialSecurityCard;

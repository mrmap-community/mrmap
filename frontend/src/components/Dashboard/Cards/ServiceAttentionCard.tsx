import { Link, useCreatePath, useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  Alert,
  Button,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";

import SimpleCard from "../../MUI/SimpleCard";
import useServiceAlerts from "../../Resource/ServiceAlert/useServiceAlerts";

/** the alerts list narrowed to the catalogues: the api answers the kind of
 *  service an alert belongs to (registry/views/alerts.py), so the lens which
 *  leads from "three catalogues harvested badly" to the alerts of the
 *  catalogues is a filter the alerts list already accepts (#1086) */
const CATALOGUE_ALERTS_FILTER = { serviceType: "CatalogueService" };

/** whether an api error says the caller may not read the alerts at all - the
 *  same reading of the http status by which the context of the system status
 *  decides about its indicator (#833): a read which is not allowed is an
 *  absent card, a read which merely failed is a problem of the deployment */
const isUnauthorized = (error: unknown): boolean => {
  const e = error as { status?: number; response?: { status?: number } };
  const status = e?.status ?? e?.response?.status;
  return status === 401 || status === 403;
};

/**
 * The services of the deployment which carry a problem, as a compact summary.
 *
 * The card answers the top rows of the alerts, most severe first, and each row
 * links to the service behind the alert; the header links to the list of all
 * alerts and to the same list narrowed to the catalogues. Its answer differs
 * per state of the read, so that none of them reads as a deployment without a
 * problem and none of it pushes the caller away from the dashboard:
 *
 * - the read which is out answers the card with a progress mark, because a
 *   card which is simply absent is read as "no service carries a problem";
 * - a deployment without an alert answers nothing, so a healthy deployment
 *   shows neither a card nor an empty card;
 * - a read the caller may not perform answers nothing and never redirects,
 *   because the card is an administrator view (#1804 coordinates access bugs);
 * - a read the api refuses answers an error, because the deployment may well
 *   have alerts which nobody can count right now.
 */
const ServiceAttentionCard = () => {
  const { data = [], total, error, isPending } = useServiceAlerts();
  const translate = useTranslate();
  const createPath = useCreatePath();
  if (isUnauthorized(error)) return null;

  const alertsList = createPath({ resource: "ServiceAlert", type: "list" });
  // the layout answers a resolvable height for its content column, so the
  // "100%" of the summary tiles would stretch this card over the whole page -
  // a single card above the rows is as high as its problems are
  const cardProps = { sx: { boxShadow: 4, height: "auto" } };
  const contentProps = { sx: { pt: 0.5, pb: 1 } };
  const cardHeader = { title: translate("serviceAlerts.title") };
  if (isPending) {
    return (
      <SimpleCard
        {...cardHeader}
        cardProps={cardProps}
        contentProps={contentProps}
      >
        <LinearProgress aria-label={translate("serviceAlerts.checking")} />
      </SimpleCard>
    );
  }
  if (error) {
    // the failing of the read is answered instead of disappearing: an absent
    // card is read as "no service carries a problem"
    return (
      <SimpleCard
        title={translate("serviceAlerts.title")}
        cardProps={cardProps}
        contentProps={contentProps}
      >
        <Alert severity="error">
          {translate("serviceAlerts.loadError")}{" "}
          <Link to={alertsList}>{translate("serviceAlerts.viewAll")}</Link>
        </Alert>
      </SimpleCard>
    );
  }
  if (!total) return null;

  return (
    <SimpleCard
      title={translate("serviceAlerts.title")}
      subheader={translate("serviceAlerts.count", { smart_count: total })}
      cardProps={cardProps}
      headerProps={{
        // the rows answer the attention of every kind of service and can be
        // out-numbered on screen by the monitoring alerts of map services;
        // beside "view all" the lens opens the very list narrowed to the
        // catalogues, so the harvesting of the deployment is always reachable
        action: (
          <Stack direction="row" spacing={1}>
            <Button component={Link} size="small" to={alertsList}>
              {translate("serviceAlerts.viewAll")}
            </Button>
            <Button
              component={Link}
              size="small"
              to={{
                pathname: alertsList,
                search: `filter=${JSON.stringify(CATALOGUE_ALERTS_FILTER)}`,
              }}
            >
              {translate("serviceAlerts.viewCatalogueAlerts")}
            </Button>
          </Stack>
        ),
      }}
      contentProps={contentProps}
    >
      <Stack spacing={0.5}>
        {data.map((record) => (
          <Stack
            key={record.id}
            direction="row"
            spacing={1}
            sx={{ alignItems: "center" }}
          >
            {record.severity === "error" ? (
              <ErrorIcon color="error" fontSize="small" />
            ) : (
              <WarningAmberIcon color="warning" fontSize="small" />
            )}
            <Typography variant="body2">
              <Link to={record.targetPath}>{record.serviceTitle}</Link>
              {" — "}
              {translate(`serviceAlerts.categories.${record.category}`)}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </SimpleCard>
  );
};

export default ServiceAttentionCard;

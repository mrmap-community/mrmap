import { Link, useCreatePath, useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Button, Stack, Typography } from "@mui/material";

import SimpleCard from "../../MUI/SimpleCard";
import useServiceAlerts from "../../Resource/ServiceAlert/useServiceAlerts";

/** the alerts list narrowed to the catalogues: the api answers the kind of
 *  service an alert belongs to (registry/views/alerts.py), so the lens which
 *  leads from "three catalogues harvested badly" to the alerts of the
 *  catalogues is a filter the alerts list already accepts (#1086) */
const CATALOGUE_ALERTS_FILTER = { serviceType: "CatalogueService" };

const ServiceAttentionCard = () => {
  const { data = [], total, error, isPending } = useServiceAlerts();
  const translate = useTranslate();
  const createPath = useCreatePath();
  if (error || isPending || !total) return null;
  const alertsList = createPath({ resource: "ServiceAlert", type: "list" });
  return (
    <SimpleCard
      title={translate("serviceAlerts.title")}
      subheader={translate("serviceAlerts.count", { smart_count: total })}
      // the layout answers a resolvable height for its content column, so the
      // "100%" of the summary tiles would stretch this card over the whole
      // page - a single card above the rows is as high as its problems are
      cardProps={{ sx: { boxShadow: 4, height: "auto" } }}
      headerProps={{
        // the five rows answer the attention of every kind of service and can
        // be out-numbered on screen by the monitoring alerts of map services;
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
      contentProps={{ sx: { pt: 0.5, pb: 1 } }}
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

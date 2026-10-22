import { Link, useCreatePath, useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Button, Stack, Typography } from "@mui/material";

import SimpleCard from "../../MUI/SimpleCard";
import useServiceAlerts from "../../Resource/ServiceAlert/useServiceAlerts";

const ServiceAttentionCard = () => {
  const { data = [], total, error, isPending } = useServiceAlerts();
  const translate = useTranslate();
  const createPath = useCreatePath();
  if (error || isPending || !total) return null;
  return (
    <SimpleCard
      title={translate("serviceAlerts.title")}
      subheader={translate("serviceAlerts.count", { smart_count: total })}
      // the layout answers a resolvable height for its content column, so the
      // "100%" of the summary tiles would stretch this card over the whole
      // page - a single card above the rows is as high as its problems are
      cardProps={{ sx: { boxShadow: 4, height: "auto" } }}
      headerProps={{
        action: (
          <Button
            component={Link}
            size="small"
            to={createPath({ resource: "ServiceAlert", type: "list" })}
          >
            {translate("serviceAlerts.viewAll")}
          </Button>
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

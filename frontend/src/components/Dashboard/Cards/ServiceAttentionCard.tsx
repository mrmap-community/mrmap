import { Link, useCreatePath, useTranslate } from "react-admin";

import { Alert, Button, Stack } from "@mui/material";

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
      footer={
        <Button
          component={Link}
          to={createPath({ resource: "ServiceAlert", type: "list" })}
        >
          {translate("serviceAlerts.viewAll")}
        </Button>
      }
    >
      <Stack spacing={1}>
        {data.map((record) => (
          <Alert
            key={record.id}
            severity={record.severity === "error" ? "error" : "warning"}
          >
            <Link to={record.targetPath}>{record.serviceTitle}</Link>
            {" — "}
            {translate(`serviceAlerts.categories.${record.category}`)}
          </Alert>
        ))}
      </Stack>
    </SimpleCard>
  );
};

export default ServiceAttentionCard;

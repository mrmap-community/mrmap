import { DateField, FunctionField, TextField, useTranslate } from "react-admin";

import { Chip } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { useFilterInputForOperation } from "../../../jsonapi/hooks/useFilterInputForOperation";
import { ALERT_REFETCH_INTERVAL } from "./useServiceAlerts";

const ListServiceAlert = () => {
  const translate = useTranslate();
  const filters = useFilterInputForOperation("list_ServiceAlert").map(
    (definition) => ({
      ...definition,
      props: {
        ...definition.props,
        label: `resources.ServiceAlert.fields.${definition.props.source}`,
      },
    }),
  );
  return (
    <ListGuesser
      realtime
      additionalFilters={filters}
      refetchInterval={ALERT_REFETCH_INTERVAL}
      sort={{ field: "severity,-occurredAt", order: "ASC" }}
      rowActions={<></>}
      dataGridProps={{
        bulkActionButtons: false,
        rowClick: (_id, _resource, record) => record.targetPath,
      }}
      columns={[
        <FunctionField
          key="severity"
          source="severity"
          render={(record) => (
            <Chip
              size="small"
              color={record.severity === "error" ? "error" : "warning"}
              label={translate(`serviceAlerts.${record.severity}`)}
            />
          )}
        />,
        <FunctionField
          key="category"
          source="category"
          sortable={false}
          render={(record) =>
            translate(`serviceAlerts.categories.${record.category}`)
          }
        />,
        <TextField key="serviceType" source="serviceType" sortable={false} />,
        <TextField key="serviceTitle" source="serviceTitle" sortable={false} />,
        <DateField key="occurredAt" source="occurredAt" showTime />,
      ]}
    />
  );
};

export default ListServiceAlert;

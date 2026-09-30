import {
  BooleanField,
  DateField,
  Show,
  type ShowProps,
  SimpleShowLayout,
  TextField,
  useRecordContext,
  WrapperField,
} from "react-admin";

import ListGuesser from "../../../jsonapi/components/ListGuesser";

const MonitoringRunDetails = () => {
  const record = useRecordContext();
  if (!record) return null;

  const relatedResource = {
    resource: "WebMapServiceMonitoringRun",
    id: record.id,
  };

  return (
    <SimpleShowLayout>
      <TextField source="id" />
      <BooleanField source="success" />
      <DateField source="dateCreated" showTime />
      <DateField source="dateDone" showTime />
      {["GetCapabilitiesProbeResult", "GetMapProbeResult"].map((resource) => (
        <WrapperField key={resource} label={resource}>
          <ListGuesser
            title={false}
            resource={resource}
            relatedResource={relatedResource}
            disableSyncWithLocation
            actions={false}
            filters={undefined}
            defaultSelectedColumns={[
              ...(resource === "GetCapabilitiesProbeResult"
                ? [
                    "checkResponseIsValidXmlSuccess",
                    "checkResponseIsValidXmlMessage",
                    "checkResponseDoesContainSuccess",
                    "checkResponseDoesContainMessage",
                  ]
                : ["checkResponseImageSuccess", "checkResponseImageMessage"]),
              "checkResponseDoesNotContainSuccess",
              "checkResponseDoesNotContainMessage",
            ]}
          />
        </WrapperField>
      ))}
    </SimpleShowLayout>
  );
};

const ShowWebMapServiceMonitoringRun = (props: ShowProps) => (
  <Show {...props}>
    <MonitoringRunDetails />
  </Show>
);

export default ShowWebMapServiceMonitoringRun;

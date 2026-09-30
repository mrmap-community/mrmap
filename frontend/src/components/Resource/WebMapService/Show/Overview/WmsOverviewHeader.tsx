import { Card, Chip } from "@mui/material";
import {
  Labeled,
  type RaRecord,
  SimpleShowLayout,
  TextField,
  UrlField,
  useRecordContext,
  WithRecord,
} from "react-admin";
import { prepareGetCapabilititesUrl } from "../../../../../ows-lib/OwsContext/utils";

const WmsOverviewHeader = () => {
  const record = useRecordContext();
  return (
    <Card
      variant="outlined"
      sx={{ width: "100%", minWidth: 0, height: "100%" }}
    >
      <SimpleShowLayout sx={{ p: 2, overflowWrap: "anywhere" }}>
        <TextField source="id" />
        <TextField source="title" />
        <TextField source="abstract" />
        <Labeled label="version">
          <Chip
            variant="outlined"
            label={String(record?.version)?.split("").join(".")}
          />
        </Labeled>
        <WithRecord
          label="GetCapabilities URL"
          //label="show remote capabilities"
          render={(record: RaRecord) => {
            const url = record.operationUrls?.find(
              (operationUrl: RaRecord) =>
                operationUrl.operation === 1 && operationUrl.method === 1,
            );
            url.url = prepareGetCapabilititesUrl(
              url.url,
              "WMS",
              record.version.toString().split("").join("."),
            ).href;
            return url ? <UrlField record={url} source="url" /> : null;
          }}
        />
      </SimpleShowLayout>
    </Card>
  );
};

export default WmsOverviewHeader;

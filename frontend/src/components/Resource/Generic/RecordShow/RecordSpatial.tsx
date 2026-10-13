import {
  Alert,
  Box,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import { useRecordContext, useTranslate, type RaRecord } from "react-admin";
import type { GeoJSON } from "geojson";
import GeoJsonMap from "../../../MapContainer/GeoJsonMap";
import FeatureGroupEditor from "../../../Input/FeatureGroupEditor";
import { getCoverageBounds } from "../../DatasetMetadataRecord/coverage";
import SimpleCard from "../../../MUI/SimpleCard";
import RecordFields, { IncludedRecordFields } from "./RecordFields";

const RecordSpatial = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const bounds = getCoverageBounds(record?.boundingGeometry);
  const geometry: GeoJSON | undefined = bounds
    ? typeof record?.boundingGeometry === "string"
      ? JSON.parse(record.boundingGeometry)
      : record?.boundingGeometry
    : undefined;
  if (!record) return null;
  return (
    <Grid container spacing={2}>
      <Grid size={12}>
        <SimpleCard title={translate("recordShow.spatial")}>
          {bounds ? (
            <GeoJsonMap id={`${record.id}-extent`}>
              <FeatureGroupEditor geoJson={geometry} editable={false} />
            </GeoJsonMap>
          ) : (
            <Alert severity="info">
              {translate("datasetExplorer.missingCoverage")}
            </Alert>
          )}
          <RecordFields
            sources={["referenceSystems", "equivalentScale", "groundRes"]}
          />
          {record.previewImage && (
            <Box
              component="img"
              src={record.previewImage}
              alt={translate("recordShow.preview")}
              sx={{ maxWidth: "100%", maxHeight: 240 }}
            />
          )}
        </SimpleCard>
      </Grid>
      <Grid size={12}>
        <SimpleCard title={translate("recordShow.time")}>
          {record.timeExtents?.length ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  {["begin", "end", "resolution", "isRelative"].map(
                    (source) => (
                      <TableCell key={source}>
                        {translate(`recordShow.${source}`)}
                      </TableCell>
                    ),
                  )}
                </TableRow>
              </TableHead>
              <TableBody>
                {record.timeExtents.map((extent: RaRecord) => (
                  <TableRow key={extent.id}>
                    {["begin", "end", "resolution", "isRelative"].map(
                      (source) => (
                        <TableCell key={source}>
                          <IncludedRecordFields
                            resource="TimeExtent"
                            record={extent}
                            sources={[source]}
                          />
                        </TableCell>
                      ),
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Alert severity="info">{translate("recordShow.noTime")}</Alert>
          )}
        </SimpleCard>
      </Grid>
    </Grid>
  );
};

export default RecordSpatial;

import { Stack } from "@mui/material";
import {
  BasenameContextProvider,
  useShowContext,
  useTranslate,
} from "react-admin";
import { Route, Routes } from "react-router-dom";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";

function RecordList({ resource }: { resource: string }) {
  const translate = useTranslate();
  const operation = useOperation(
    `list_related_${resource}_of_CatalogueService`,
  );
  if (!operation) return null;
  return (
    <SimpleCard
      title={translate(`resources.${resource}.name`, {
        smart_count: 2,
        _: resource,
      })}
      cardProps={{ variant: "outlined" }}
    >
      <ServiceRelatedTab
        resource={resource}
        defaultSelectedColumns={["title", "abstract"]}
      />
    </SimpleCard>
  );
}

export default function Records() {
  const { record } = useShowContext();
  if (!record) return null;
  // Each list gets a distinct route so its edit dialog cannot open for the other resource.
  return (
    <BasenameContextProvider
      basename={`/CatalogueService/${record.id}/show/records`}
    >
      <Routes>
        <Route
          path="DatasetMetadataRecord/*"
          element={<RecordList resource="DatasetMetadataRecord" />}
        />
        <Route
          path="ServiceMetadataRecord/*"
          element={<RecordList resource="ServiceMetadataRecord" />}
        />
        <Route
          path="*"
          element={
            <Stack spacing={2}>
              <RecordList resource="DatasetMetadataRecord" />
              <RecordList resource="ServiceMetadataRecord" />
            </Stack>
          }
        />
      </Routes>
    </BasenameContextProvider>
  );
}

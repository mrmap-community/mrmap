import { Stack } from "@mui/material";
import { ResourceContext, useRecordContext } from "react-admin";
import ListAllowedWebMapServiceOperation from "../../../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation";
import SpatialPolicyTester from "../Overview/SpatialSecurity/SpatialPolicyTester";

export const SpatialSecureTab = () => {
  const record = useRecordContext();
  return (
    <Stack spacing={2}>
      <SpatialPolicyTester />
      <ResourceContext value="AllowedWebMapServiceOperation">
        <ListAllowedWebMapServiceOperation
          listGuesserProps={{
            relatedResource: { resource: "WebMapService", id: record?.id },
            disableSyncWithLocation: true,
          }}
        />
      </ResourceContext>
    </Stack>
  );
};

export default SpatialSecureTab;

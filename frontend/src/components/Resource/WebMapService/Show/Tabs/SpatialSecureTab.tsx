import { ResourceContext, useRecordContext } from "react-admin";

import { Stack } from "@mui/material";

import ListAllowedWebMapServiceOperation from "../../../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation";
import AccessRulesSummary from "../../../Generic/ServiceShow/AccessRulesSummary";
import SpatialPolicyTester from "../Overview/SpatialSecurity/SpatialPolicyTester";

export const SpatialSecureTab = () => {
  const record = useRecordContext();
  return (
    <Stack spacing={2}>
      <AccessRulesSummary
        ruleResource="AllowedWebMapServiceOperation"
        serviceId={record?.id}
      />
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

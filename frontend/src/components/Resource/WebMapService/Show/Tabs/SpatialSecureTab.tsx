import { ResourceContext, useRecordContext } from "react-admin";

import { Stack } from "@mui/material";

import ListAllowedWebMapServiceOperation from "../../../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation";
import AccessRulesSummary from "../../../Generic/ServiceShow/AccessRulesSummary";
import { ServiceEmptyList } from "../../../Generic/ServiceShow/ServiceRelatedTab";
import SpatialPolicyTester from "../Overview/SpatialSecurity/SpatialPolicyTester";

export const SpatialSecureTab = () => {
  const record = useRecordContext();
  const summary = (
    <AccessRulesSummary
      ruleResource="AllowedWebMapServiceOperation"
      serviceId={record?.id}
    />
  );
  return (
    <Stack spacing={2}>
      <ResourceContext value="AllowedWebMapServiceOperation">
        <ListAllowedWebMapServiceOperation
          listGuesserProps={{
            relatedResource: { resource: "WebMapService", id: record?.id },
            disableSyncWithLocation: true,
            listContent: summary,
            empty: <ServiceEmptyList />,
            queryOptions: {
              meta: { jsonApiParams: { include: "operations,allowedGroups,securedLayers" } },
            },
          }}
        />
      </ResourceContext>
      <SpatialPolicyTester />
    </Stack>
  );
};

export default SpatialSecureTab;

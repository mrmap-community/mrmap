import type { ServiceProtocol } from "../ServiceShow/ServiceDetailsCard";

import { useGetRecordRepresentation, useResourceContext, useTranslate } from "react-admin";

import { Stack } from "@mui/material";

import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import HistoryList from "../History/HistoryList";
import SelectedServiceDetailsCard from "../ServiceShow/SelectedServiceDetailsCard";

/**
 * The aside of the screen of the registered services of one kind of service.
 *
 * The card of the service which is selected comes first, because a screen of
 * services is navigated by looking at one service after another: its identity,
 * the states which need attention and the outcome of its last run and job are
 * answered above the changelog, and the way to the screen of the service is
 * offered next to its identity. The changelog is asked for the selected service
 * when there is one and for all services of the resource when there is none,
 * which its subheader names.
 */
const ServiceListAside = ({ protocol }: { protocol: ServiceProtocol }) => {
  const resource = useResourceContext();
  const historyResource = `Historical${resource}`;
  const historyOperation = useOperation(`list_${historyResource}`);
  const {selectedRecord} = useSelectedRecordContext()
  const getRecordRepresentation = useGetRecordRepresentation(resource)
  const translate = useTranslate();

  return (
    <Stack
      spacing={2}
      sx={{
        ml: { xs: 0, md: 2 },
        mt: { xs: 2, md: 0 },
        width: { xs: "100%", md: 360, xl: 440 },
        minWidth: 0,
        flexShrink: 0,
        alignSelf: "flex-start",
      }}
    >
      <SelectedServiceDetailsCard protocol={protocol} />
      {historyOperation && resource && (
        <SimpleCard
          headerProps={{ sx: { flexShrink: 0 } }}
          contentProps={{
            sx: { p: 0, minHeight: 0, overflowY: "auto", '&:last-child': { pb: 0 } },
          }}
          cardProps={{
            variant: "outlined",
            sx: { width: "100%", maxHeight: 360, display: "flex", flexDirection: "column", overflow: "hidden" },
          }}
          title={translate("historyList.title")}
          subheader={selectedRecord
            ? translate("historyList.selectedService", {
                service: selectedRecord.title || getRecordRepresentation(selectedRecord),
              })
            : translate("historyList.allServices")}
        >
          {/* the events of the changelog belong to one service, so a new selection
              asks for the events of the service it names and not for the events of
              the service before it */}
          <HistoryList
            key={selectedRecord?.id ?? "all"}
            variant="compact"
            resource={historyResource}
            related={resource}
          />
        </SimpleCard>
      )}
    </Stack>
  );
};

export default ServiceListAside;

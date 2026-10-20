import { Stack } from "@mui/material";
import { useGetRecordRepresentation, useResourceContext } from "react-admin";
import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import HistoryList from "../../../HistoryList";
import SimpleCard from "../../../MUI/SimpleCard";
import SelectedServiceDetailsCard from "../ServiceShow/SelectedServiceDetailsCard";
import type { ServiceProtocol } from "../ServiceShow/ServiceDetailsCard";

const ServiceListAside = ({ protocol }: { protocol: ServiceProtocol }) => {
  const resource = useResourceContext();
  const historyResource = `Historical${resource}`;
  const historyOperation = useOperation(`list_${historyResource}`);
  const {selectedRecord} = useSelectedRecordContext()
  const getRecordRepresentation = useGetRecordRepresentation(resource)

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
          title={(selectedRecord === undefined) ? 'Last 10 events' : getRecordRepresentation(selectedRecord)}
        >
          <HistoryList resource={historyResource} related={resource} record={undefined} />
        </SimpleCard>
      )}
      <SelectedServiceDetailsCard protocol={protocol} />
    </Stack>
  );
};

export default ServiceListAside;

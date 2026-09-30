import { Grid } from "@mui/material";
import { useRecordContext, useResourceDefinition } from "react-admin";
import HistoryList from "../HistoryList";
import MonitoringRunsCard from "../Overview/MonitoringRuns/MonitoringRunsCard";
import UpdateJobsCard from "../Overview/UpdateJobs/UpdateJobsCard";
import WmsOverviewHeader from "../Overview/WmsOverviewHeader";

const OverviewTab = () => {
  const record = useRecordContext();
  const { name } = useResourceDefinition();
  return (
    <Grid
      container
      spacing={2}

      sx={{
        alignItems: "stretch",
        minWidth: 0,
        // Stretch the grid cells and embedded list wrappers through to each card.
        "& > .MuiGrid-root": { display: "flex", minWidth: 0 },
        "& > .MuiGrid-root > .list-page": { flex: 1, minWidth: 0 },
        "&& .RaList-main": { width: "100%", minWidth: 0, m: 0 },
      }}
    >
      <Grid size={{ xs: 12, md: 6 }}>
        <WmsOverviewHeader />
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <HistoryList
          resource={`Historical${name ?? ""}`}
          related={name ?? ""}
          record={record}
        />
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <UpdateJobsCard />
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <MonitoringRunsCard />
      </Grid>
    </Grid>
  );
};

export default OverviewTab;

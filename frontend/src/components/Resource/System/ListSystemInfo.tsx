import { Grid } from "@mui/material";
import SystemStatus from "./SystemStatus";
import SystemView from "./SystemView";

const ListSystemInfo = () => (
    <Grid
      container
      spacing={2}
      
      sx={{
        mb: 2,
        alignItems: "stretch",
        minWidth: 0,
        maxHeight: "100%",
        // Stretch the grid cells and embedded list wrappers through to each card.
        //"& > .MuiGrid-root": { display: "flex", minWidth: 0 },
        "& > .MuiGrid-root > .list-page": { flex: 1, minWidth: 0 },
        "&& .RaList-main": { width: "100%", minWidth: 0, m: 0 },
      }}
    >
      <Grid 
        size={{ xs: 12, md: 6 }}
        sx={{
          maxHeight: "100%",
        }}
      >
        <SystemView />
      </Grid>
      <Grid 
        size={{ xs: 12, md: 6 }}
        sx={{
          maxHeight: "100%",
        }}
      >
        <SystemStatus />
      </Grid>
    </Grid>
);

export default ListSystemInfo;

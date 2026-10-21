import { Children, type ReactNode } from "react";

import { Grid } from "@mui/material";

import LivePreview from "./LivePreview/LivePreview";
import ServiceDetailsCard, { type ServiceProtocol } from "./ServiceDetailsCard";
import ServiceHistoryCard from "./ServiceHistoryCard";

const ServiceOverview = ({
  protocol,
  history = <ServiceHistoryCard />,
  children,
  spatialSecurity,
  preview = protocol === "CSW" ? <LivePreview protocol={protocol} /> : null,
}: {
  protocol: ServiceProtocol;
  history?: ReactNode;
  children?: ReactNode;
  spatialSecurity?: ReactNode;
  preview?: ReactNode;
}) => {
  return (
    <Grid
      container
      spacing={2}
      sx={{
        alignItems: "stretch",
        minWidth: 0,
        "& > .MuiGrid-root": { display: "flex", minWidth: 0 },
        "& > .MuiGrid-root > .list-page": { flex: 1, minWidth: 0 },
        "&& .RaList-main": { width: "100%", minWidth: 0, m: 0 },
      }}
    >
      <Grid size={{ xs: 12, md: 6 }}>
        <ServiceDetailsCard protocol={protocol} />
      </Grid>
      {history && <Grid size={{ xs: 12, md: 6 }}>{history}</Grid>}
      {preview && <Grid size={12}>{preview}</Grid>}
      {spatialSecurity && <Grid size={12}>{spatialSecurity}</Grid>}
      {Children.map(
        children,
        (child) => child && <Grid size={{ xs: 12, md: 6 }}>{child}</Grid>,
      )}
    </Grid>
  );
};

export default ServiceOverview;

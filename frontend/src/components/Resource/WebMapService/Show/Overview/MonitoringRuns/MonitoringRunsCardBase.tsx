import type { PropsWithChildren } from "react";
import { useListContext, useTranslate } from "react-admin";

import { Chip } from "@mui/material";

import RunHistoryCard from "../RunHistoryCard";
import { formatMonitoringRun } from "./formatMonitoringRun";

const MonitoringRunsCardBase = ({ children }: PropsWithChildren) => {
  const { data, resource } = useListContext();
  const translate = useTranslate();
  const message = (key: string) =>
    translate(`resources.${resource}.${key}`);
  const lastRun = data?.[0];

  let color: "success" | "error" | undefined;
  if (lastRun) color = lastRun.success ? "success" : "error";

  return (
    <RunHistoryCard
      serviceFilter="service__id"
      color={color}
      getHeader={() => ({
        title: message("lastMonitoringRuns"),
        subheader:
          lastRun?.dateCreated &&
          formatMonitoringRun(lastRun.dateCreated, lastRun.dateDone),
        action: lastRun ? (
          <Chip
            size="small"
            color={lastRun.success ? "success" : "error"}
            variant={lastRun.success ? "outlined" : "filled"}
            label={message(lastRun.success ? "passed" : "failed")}
          />
        ) : undefined,
      })}
    >
      {children}
    </RunHistoryCard>
  );
};

export default MonitoringRunsCardBase;

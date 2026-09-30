import type { PropsWithChildren } from "react";
import { useListContext, useTranslate } from "react-admin";

import { Chip } from "@mui/material";

import RunHistoryCard from "../RunHistoryCard";

const UpdateJobsCardBase = ({ children }: PropsWithChildren) => {
  const { data } = useListContext();
  const translate = useTranslate();
  const message = (key: string) =>
    translate(`resources.WebMapServiceUpdateJob.${key}`);
  const hasJobs = (data?.length ?? 0) > 0;
  const reviewCount = data?.filter((job) => job.statusCode === 2).length ?? 0;
  const reviewRequired = reviewCount > 0;

  return (
    <RunHistoryCard
      resource="WebMapServiceUpdateJob"
      settingsResource="WebMapServiceUpdateSetting"
      serviceFilter="service"
      color={reviewRequired ? "warning" : hasJobs ? "success" : undefined}
      getHeader={(overdue) => ({
        title: message(reviewRequired ? "reviewRequired" : "lastUpdateJobs"),
        subheader:
          hasJobs && !overdue
            ? message(
                reviewRequired
                  ? "reviewRequiredSubheader"
                  : "lastUpdateJobsSubheader",
              )
            : undefined,
        action: reviewRequired ? (
          <Chip size="small" color="warning" label={`${reviewCount} open`} />
        ) : hasJobs && !overdue ? (
          <Chip
            size="small"
            color="success"
            variant="outlined"
            label={data?.[0]?.status}
          />
        ) : undefined,
      })}
    >
      {children}
    </RunHistoryCard>
  );
};

export default UpdateJobsCardBase;

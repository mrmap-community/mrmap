import type { PropsWithChildren } from "react";
import { useListContext, useRecordContext, useTranslate } from "react-admin";

import { Chip, Divider, Stack } from "@mui/material";

import RunServiceUpdateButton from "../../../../Generic/ServiceShow/RunServiceUpdateButton";
import RunHistoryCard from "../RunHistoryCard";
import { LayerChangesChart } from "./UpdateJobChangeChart";

export interface UpdateJobsCardBaseProps extends PropsWithChildren {
  resource: string;
  settingsResource: string;
}

const UpdateJobsCardBase = ({ children }: UpdateJobsCardBaseProps) => {
  const { data, resource } = useListContext();

  const service = useRecordContext();
  const translate = useTranslate();
  const message = (key: string) => translate(`resources.${resource}.${key}`);
  const hasJobs = (data?.length ?? 0) > 0;
  const reviewCount = data?.filter((job) => job.statusCode === 2).length ?? 0;
  const reviewRequired = reviewCount > 0;
  

  return (
    <RunHistoryCard
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
        action: (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <RunServiceUpdateButton
              resource={resource}
              serviceId={service?.id}
            />
            {reviewRequired ? (
              <Chip
                size="small"
                color="warning"
                label={`${reviewCount} open`}
              />
            ) : hasJobs && !overdue ? (
              <Chip
                size="small"
                color="success"
                variant="outlined"
                label={data?.[0]?.status}
              />
            ) : null}
          </Stack>
        ),
      })}
    >
      <LayerChangesChart/>
      <Divider />
      {children}
    </RunHistoryCard>
  );
};

export default UpdateJobsCardBase;

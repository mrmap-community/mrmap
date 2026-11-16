import type { PropsWithChildren } from "react";
import { type ReactNode } from "react";
import { useListContext, useRecordContext, useTranslate } from "react-admin";

import { Chip, Divider, Stack } from "@mui/material";

import RunServiceUpdateButton from "../../../../Generic/ServiceShow/RunServiceUpdateButton";
import RunHistoryCard from "../RunHistoryCard";
import { LayerChangesChart } from "./UpdateJobChangeChart";

export type UpdateJobsCardBaseProps = PropsWithChildren

const UpdateJobsCardBase = ({ children }: UpdateJobsCardBaseProps) => {
  const { data, resource } = useListContext();

  const service = useRecordContext();
  const translate = useTranslate();
  const message = (key: string) => translate(`resources.${resource}.${key}`);
  const hasJobs = (data?.length ?? 0) > 0;
  const reviewCount = data?.filter((job) => job.statusCode === 2).length ?? 0;
  const reviewRequired = reviewCount > 0;

  let color: "warning" | "success" | undefined;
  if (reviewRequired) color = "warning";
  else if (hasJobs) color = "success";

  return (
    <RunHistoryCard
      serviceFilter="service"
      color={color}
      getHeader={(overdue) => {
        let subheader: string | undefined;
        if (hasJobs && !overdue) {
          subheader = message(
            reviewRequired
              ? "reviewRequiredSubheader"
              : "lastUpdateJobsSubheader",
          );
        }

        let statusChip: ReactNode = null;
        if (reviewRequired) {
          statusChip = (
            <Chip size="small" color="warning" label={`${reviewCount} open`} />
          );
        } else if (hasJobs && !overdue) {
          statusChip = (
            <Chip
              size="small"
              color="success"
              variant="outlined"
              label={data?.[0]?.status}
            />
          );
        }

        return {
          title: message(reviewRequired ? "reviewRequired" : "lastUpdateJobs"),
          subheader,
          action: (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <RunServiceUpdateButton
                resource={resource}
                serviceId={service?.id}
              />
              {statusChip}
            </Stack>
          ),
        };
      }}
    >
      <LayerChangesChart resource={resource} />
      <Divider />
      {children}
    </RunHistoryCard>
  );
};

export default UpdateJobsCardBase;

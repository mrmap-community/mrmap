import { type ReactNode } from "react";
import { useTranslate } from "react-admin";

import SyncIcon from "@mui/icons-material/Sync";
import { type Theme, useMediaQuery } from "@mui/material";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";

import { Count } from "../../../../jsonapi/components/Count";
import { useBackgroundJobCenter } from "./BackgroundJobCenterContext";
import {
  COUNTS_POLL_MILLISECONDS,
  JOB_COUNT_FILTERS,
  JOB_COUNT_SORT,
} from "./counts";

/**
 * The activity counters of the app bar (#1206).
 *
 * One control which tells, without opening anything, how much work is
 * running, waiting and broken - and opens the Background Job Center. The
 * numbers are answered by the collection endpoint (`Count`), not by the
 * client-side store, so they stay accurate while the deployment churns
 * thousands of processes and the store holds only a bounded window of them.
 * On narrow screens the words give way to a badge over the icon.
 */
const JobCount = ({ filter }: { filter: Record<string, string> }): ReactNode => (
  <Count
    resource="BackgroundProcess"
    filter={filter}
    sort={JOB_COUNT_SORT}
    refetchInterval={COUNTS_POLL_MILLISECONDS}
    variant="inherit"
    component="span"
  />
);

const JobCenterIndicator = (): ReactNode => {
  const translate = useTranslate();
  const { setOpen } = useBackgroundJobCenter();
  const isWideEnough = useMediaQuery<Theme>((theme) =>
    theme.breakpoints.up("sm"),
  );

  const label = translate("backgroundActivity.jobCenter.title");

  if (isWideEnough) {
    return (
      <Button
        color="inherit"
        size="small"
        startIcon={<SyncIcon />}
        onClick={() => setOpen(true)}
        aria-label={label}
        sx={{
          textTransform: "none",
          border: 1,
          borderColor: "action.disabledBackground",
          borderRadius: 2,
          gap: 0.5,
        }}
      >
        <Typography component="span" variant="body2">
          <JobCount filter={JOB_COUNT_FILTERS.running} />{" "}
          {translate("backgroundActivity.jobCenter.tabs.running")}
        </Typography>
        <Typography component="span" variant="body2">
          · <JobCount filter={JOB_COUNT_FILTERS.waiting} />{" "}
          {translate("backgroundActivity.jobCenter.tabs.waiting")}
        </Typography>
        <Typography
          component="span"
          variant="body2"
          color="error.light"
        >
          · <JobCount filter={JOB_COUNT_FILTERS.failed} />{" "}
          {translate("backgroundActivity.jobCenter.tabs.failed")}
        </Typography>
      </Button>
    );
  }

  return (
    <IconButton color="inherit" onClick={() => setOpen(true)} aria-label={label}>
      <SyncIcon />
    </IconButton>
  );
};

export default JobCenterIndicator;

import { useTranslate } from "react-admin";

import { SxProps, Step, StepLabel, Stepper, Typography } from "@mui/material";

/**
 * The three workflow stages of a harvesting run with the state the run is in.
 *
 * `sx` places the stepper in the screen which shows it: the show screen of a
 * run gives it room, a row of the list of runs keeps it dense.
 */
const HarvestingPhaseStepper = ({
  phase,
  sx,
}: {
  phase: number | undefined;
  sx?: SxProps;
}) => {
  const translate = useTranslate();
  // Map the API's phases to the three user-facing workflow stages.
  const activeStep =
    phase === 0 || phase === 1
      ? 0
      : phase === 2
        ? 1
        : phase === 3
          ? 2
          : phase === 4
            ? 3
            : -1;
  return (
    <Stepper activeStep={activeStep} alternativeLabel sx={sx ?? { my: 2 }}>
      {["discover", "download", "import"].map((stage, index) => {
        const state =
          activeStep < 0
            ? "unknown"
            : activeStep > index
              ? "completed"
              : activeStep === index && phase !== 0
                ? "inProgress"
                : "waiting";
        const label = translate(`harvestingActivity.stages.${stage}`);
        const status = translate(`harvestingActivity.stageStatus.${state}`);
        return (
          <Step
            key={stage}
            completed={activeStep > index}
            aria-label={`${label}: ${status}`}
          >
            <StepLabel
              optional={
                <Typography variant="caption" color="text.secondary">
                  {status}
                </Typography>
              }
            >
              {label}
            </StepLabel>
          </Step>
        );
      })}
    </Stepper>
  );
};

export default HarvestingPhaseStepper;

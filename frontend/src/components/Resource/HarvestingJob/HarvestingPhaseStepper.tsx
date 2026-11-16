import { useTranslate } from "react-admin";

import { SxProps, Step, StepLabel, Stepper, Typography } from "@mui/material";

/**
 * The three workflow stages of a harvesting run with the state the run is in.
 *
 * `sx` places the stepper in the screen which shows it: the show screen of a
 * run gives it room, a row of the list of runs keeps it dense.
 */
/** the workflow step each API phase of the harvesting job answers */
const STEP_BY_PHASE: Record<number, number> = { 0: 0, 1: 0, 2: 1, 3: 2, 4: 3 };

const HarvestingPhaseStepper = ({
  phase,
  sx,
}: {
  phase: number | undefined;
  sx?: SxProps;
}) => {
  const translate = useTranslate();
  // Map the API's phases to the three user-facing workflow stages; the very
  // first phase and an unknown one leave the stepper without an active step.
  const activeStep = phase === undefined ? -1 : STEP_BY_PHASE[phase] ?? -1;
  return (
    <Stepper activeStep={activeStep} alternativeLabel sx={sx ?? { my: 2 }}>
      {["discover", "download", "import"].map((stage, index) => {
        let state: "unknown" | "completed" | "inProgress" | "waiting";
        if (activeStep < 0) state = "unknown";
        else if (activeStep > index) state = "completed";
        else if (activeStep === index && phase !== 0) state = "inProgress";
        else state = "waiting";
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

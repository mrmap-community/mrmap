import Box from '@mui/material/Box';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import Typography from '@mui/material/Typography';

import { type FormDefinition, useWizardFormContext, WizardFormBase, type WizardStepDefinition } from './WizardFormContext';

export interface WizardFormProps {
  steps?: WizardStepDefinition[];
  activeStep?: number;
}

const WizardFormCore = () => { 
  const {steps, activeStep, errors, setActiveStep} = useWizardFormContext();

  const getStepError = (step: WizardStepDefinition): string | undefined => {
    const currentError = errors.find(([key]) => key === step.id);
    return currentError?.[1];
  };

  const isStepCompleted = (step: WizardStepDefinition): boolean => {
    if (typeof step.isCompleted === 'function') {
      return step.isCompleted();
    }

    return Boolean(step.isCompleted);
  };

  return (
    <Box sx={{ width: '100%' }}>
      <Stepper activeStep={activeStep} alternativeLabel>
        {steps.map((step, index) => {
          const labelProps: {
            optional?: React.ReactNode;
            error?: boolean;
          } = {};

          const stepError = getStepError(step);
          const completed = isStepCompleted(step);

          if (stepError) {
            labelProps.optional = (
              <Typography variant="caption" color="error">
                {stepError}
              </Typography>
            );
            labelProps.error = true;
          } else if (completed) {
            labelProps.optional = <Typography variant="caption" color="success.main">Completed</Typography>;
          } else if (step.optional) {
            labelProps.optional = step.optional;
          }

          return (
            <Step
              key={step.id ?? `${step.label}-${index}`}
              completed={completed}
              onClick={() => setActiveStep(index)}
            >
              <StepLabel {...labelProps}>{step.label}</StepLabel>
            </Step>
          );
        })}
      </Stepper>

      {steps[activeStep] ? (
        <Box sx={{ mt: 3 }}>
          {steps[activeStep].content ?? steps[activeStep].component ?? null}
        </Box>
      ) : null}
    </Box>
  );
}

const WizardForm = ({
  steps,
  activeStep,
}: WizardFormProps) => {
  return (
    <WizardFormBase
      initialSteps={steps}
      initialActiveStep={activeStep}
    >
      <WizardFormCore>
      </WizardFormCore>
    </WizardFormBase>
  )
};

export type { FormDefinition };

export default WizardForm;
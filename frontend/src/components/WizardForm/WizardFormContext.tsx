import {
  createContext,
  type Dispatch,
  type PropsWithChildren,
  type ReactNode,
  type SetStateAction,
  useContext,
  useMemo,
  useState,
} from 'react';

export type WizardError = [key: string, value: string];

export interface WizardStepDefinition {
  id: string;
  label: string;
  content?: ReactNode;
  component?: ReactNode;
  optional?: ReactNode;
  isCompleted?: boolean | (() => boolean);
}

export type FormDefinition = WizardStepDefinition;

export interface WizardFormState {
  activeStep: number;
  steps: WizardStepDefinition[];
  errors: WizardError[];
  setActiveStep: Dispatch<SetStateAction<number>>;
  setErrors: Dispatch<SetStateAction<WizardError[]>>;
  setSteps: Dispatch<SetStateAction<WizardStepDefinition[]>>;
  setStepCompleted: (stepId: string, completed: boolean) => void;
  isStepCompleted: (step: number | string) => boolean;
}

export interface WizardFormBaseProps extends PropsWithChildren {
  initialSteps?: WizardStepDefinition[];
  initialActiveStep?: number;
}

export const WizardFormContext = createContext<WizardFormState | undefined>(undefined);

export const WizardFormBase = ({
  children,
  initialSteps = [],
  initialActiveStep = 0,
}: WizardFormBaseProps): ReactNode => {
  const [errors, setErrors] = useState<WizardError[]>([]);
  const [steps, setSteps] = useState<WizardStepDefinition[]>(initialSteps);
  const [activeStep, setActiveStep] = useState(initialActiveStep);


  const setStepCompleted = (stepId: string, completed: boolean): void => {
    setSteps((currentSteps) =>
      currentSteps.map((step) =>
        step.id === stepId
          ? {
              ...step,
              isCompleted: completed,
            }
          : step,
      ),
    );
  };

  const isStepCompleted = (step: number | string): boolean => {
    const index = typeof step === 'number' ? step : steps.findIndex((currentStep) => currentStep.id === step);

    if (index === -1) {
      return false;
    }

    const currentStep = steps[index];

    if (typeof currentStep.isCompleted === 'function') {
      return currentStep.isCompleted();
    }

    return Boolean(currentStep.isCompleted);
  };

  const value = useMemo<WizardFormState>(
    () => ({
      activeStep,
      errors,
      isStepCompleted,
      setActiveStep,
      setErrors,
      setStepCompleted,
      setSteps,
      steps,
    }),
    [activeStep, errors, steps],
  );

  return <WizardFormContext.Provider value={value}>{children}</WizardFormContext.Provider>;
};

export const useWizardFormContext = (): WizardFormState => {
  const wizardFormContext = useContext(WizardFormContext);

  if (wizardFormContext === undefined) {
    throw new Error('wizardFormContext must be inside a WizardFormBase');
  }

  return wizardFormContext;
};

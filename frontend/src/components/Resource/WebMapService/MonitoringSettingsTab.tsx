import { useCallback } from 'react';
import { useRecordContext } from 'react-admin';
import CreateGuesser from '../../../jsonapi/components/CreateGuesser';
import SchemaAutocompleteInput from '../../../jsonapi/components/SchemaAutocompleteInput';
import CronInput from '../../Input/CronInput';
import WizardForm from '../../WizardForm/WizardForm';
import { useWizardFormContext } from '../../WizardForm/WizardFormContext';


const FirstStep = () => {
  const record = useRecordContext();
  const {steps, activeStep, setErrors, setStepCompleted} = useWizardFormContext();
  const onSuccess = useCallback(()=>{
    setStepCompleted(steps[activeStep].id, true)
  },[steps, activeStep, setStepCompleted])

  const onError = useCallback((error: Error)=>{
    setErrors((currentErrors) => {
      const newErrors = currentErrors.filter(([key]) => key !== steps[activeStep].id);
      newErrors.push([steps[activeStep].id, error.message]);
      return newErrors;
    });
  },[setErrors])

  return (
    <CreateGuesser
      resource='WebMapServiceMonitoringSetting'
      mutationOptions={{onSuccess, onError}}
      defaultValues={{
        "service": record
      }}

      updateFieldDefinitions={
        [
          {
            component: CronInput, 
            props: {source: "scheduleInterval"}
          },
          {
            component: SchemaAutocompleteInput, 
            props: {source: "service", hidden: true}
          },
        ]
      }
    />
  )
}


export const MonitoringSettingsTab = () => {
  const record = useRecordContext();

  return (
    <WizardForm
      steps={
        [
          {
            id: 'aa',
            label: 'Monitoring Settings',
            content: <FirstStep/>
          }
        ]
      }
    />
  )
}

export default MonitoringSettingsTab
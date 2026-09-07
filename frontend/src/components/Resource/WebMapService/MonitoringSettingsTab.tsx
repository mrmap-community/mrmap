import { useCallback } from 'react';

import { UseCreateMutateParams, useRecordContext } from 'react-admin';
import CreateGuesser from '../../../jsonapi/components/CreateGuesser';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import SchemaAutocompleteInput from '../../../jsonapi/components/SchemaAutocompleteInput';
import CronInput from '../../Input/CronInput';
import WizardForm from '../../WizardForm/WizardForm';
import { useWizardFormContext } from '../../WizardForm/WizardFormContext';


const FirstStep = () => {
  const record = useRecordContext();
  const {steps, activeStep, setErrors, setStepCompleted} = useWizardFormContext();
  const onSuccess = useCallback((
    data: any, 
    variables: Partial<UseCreateMutateParams<any>>, 
    onMutateResult: unknown, 
    context: any
  )=>{
    setStepCompleted(steps[activeStep].id, true, data)
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

const SecondStep = () => {
  const {steps, activeStep,} = useWizardFormContext();
  
  return (
    <ListGuesser
      resource='GetCapabilitiesProbe'
      relatedResource='WebMapServiceMonitoringSetting'
      relatedResourceId={steps[activeStep-1].completedData?.id}
      
    />
  )
}


export const MonitoringSettingsTab = () => {

  return (
    <WizardForm
      steps={
        [
          {
            id: 'aa',
            label: 'Monitoring Settings',
            content: <FirstStep/>
          },
          {
            id: '2',
            label: 'GetCapabilities Probes',
            content: <SecondStep/>
          }
        ]
      }
    />
  )
}

export default MonitoringSettingsTab
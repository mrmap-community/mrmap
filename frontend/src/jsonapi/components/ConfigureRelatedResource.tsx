import _ from 'lodash';
import { useCallback, useMemo, useState } from 'react';
import { RaRecord, SaveButton, Toolbar, useNotify, useShowController, useTranslate } from 'react-admin';
import CreateGuesser from './CreateGuesser';
import EditGuesser from './EditGuesser';


export interface ConfigureRelatedResourceProps {
  relatedResource: string
  relatedName: string
  relatedResourceReverseName: string
}

const CustomToolbar = () => (
  <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
      <SaveButton alwaysEnable/>
  </Toolbar>
);

const ConfigureRelatedResource = (
  {
    relatedResource,
    relatedName,
    relatedResourceReverseName,
  }: ConfigureRelatedResourceProps
) => {
  const translate = useTranslate();
  const notify = useNotify();
  
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const { record, refetch } = useShowController();
  const [relatedObject, setRelatedObject] = useState(_.get(record, relatedName))

  const onSuccess = useCallback((data: any, variables: any, context:any)=>{
    refetch()
    setRelatedObject(data)
    notify(`resources.${relatedResource}.notifications.created`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate(`ra.notification.created`, {
              smart_count: 1,
          }),
      },
  });
  },[])

  const defaultValues = useMemo(()=> {
    const _defaultValues: any =  {}
    _defaultValues[relatedResourceReverseName] = record;
    return _defaultValues
  },[relatedName, record])
  
  const isMultiple = useMemo(()=> (Array.isArray(relatedObject)), [relatedObject])

  const editForms = useMemo(()=>(
    isMultiple ? relatedObject.map((obj: RaRecord) => (
      <EditGuesser
        key={`edit-${relatedResource}-${obj?.id}`}
        resource={relatedResource}
        id={obj?.id}
        toolbar={<CustomToolbar/>}
        redirect={false}
      /> 
    )) : <EditGuesser 
          resource={relatedResource}
          id={relatedObject?.id}
          toolbar={<CustomToolbar/>}
          redirect={false}
        /> 
  ), [isMultiple])

  if (relatedObject === null || relatedObject === undefined)
    return (
      <CreateGuesser
        resource={relatedResource}
        defaultValues={defaultValues}
        mutationOptions={{onSuccess}}
        redirect={false}
      />
    )
  return (<>{editForms}</>)
}

export default ConfigureRelatedResource
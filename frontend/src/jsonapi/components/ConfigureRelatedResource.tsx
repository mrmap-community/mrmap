import _ from 'lodash';
import { useCallback, useState } from 'react';
import { SaveButton, Toolbar, useNotify, useShowController, useTranslate } from 'react-admin';
import CreateGuesser from './CreateGuesser';
import EditGuesser from './EditGuesser';


export interface ConfigureRelatedResourceProps {
  relatedResource: string
  relatedName: string
}

const CustomToolbar = () => (
  <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
      <SaveButton alwaysEnable/>
  </Toolbar>
);

const ConfigureRelatedResource = (
  {
    relatedResource,
    relatedName
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

  if (relatedObject === null || relatedObject === undefined)
    return (
      <CreateGuesser
        resource={relatedResource}
        defaultValues={{securedService: record}}
        mutationOptions={{onSuccess}}
        redirect={false}
      />
    )
  return (
    <EditGuesser 
        resource={relatedResource}
      id={relatedObject?.id}
      toolbar={<CustomToolbar/>}
      redirect={false}
    /> 
  )
}

export default ConfigureRelatedResource
import { useCallback, useState } from 'react';
import { SaveButton, Toolbar, useNotify, useShowController, useTranslate } from 'react-admin';
import CreateGuesser from '../../../jsonapi/components/CreateGuesser';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import SchemaAutocompleteInput from '../../../jsonapi/components/SchemaAutocompleteInput';

const CustomToolbar = () => (
  <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
      <SaveButton alwaysEnable/>
  </Toolbar>
);

const ProxySettings = () => {
  const translate = useTranslate();
  const notify = useNotify();
  
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const { record, refetch } = useShowController();

  const [proxySetting, setProxySetting] = useState(record?.proxySetting)

  const onSuccess = useCallback((data: any, variables: any, context:any)=>{
    refetch()
    setProxySetting(data)
    notify(`resources.WebMapServiceProxySetting.notifications.created`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate(`ra.notification.created`, {
              smart_count: 1,
          }),
      },
  });
  },[])

  if (proxySetting === null || proxySetting === undefined)
    return (
      <CreateGuesser
        resource='WebMapServiceProxySetting'
        defaultValues={{securedService: record}}
        mutationOptions={{onSuccess}}
        redirect={false}
        updateFieldDefinitions={[
          {
            component: SchemaAutocompleteInput, 
            props: {source: "securedService", hidden: true }
          }
        ]}
      />
    )
  return (
    <EditGuesser 
      resource='WebMapServiceProxySetting'
      id={proxySetting?.id}
      toolbar={<CustomToolbar/>}
      redirect={false}
      updateFieldDefinitions={[
        {
          component: SchemaAutocompleteInput, 
          props: {source: "securedService", hidden: true }
        }
      ]}
    /> 
  )
}


const ProxySettingsTab = () => {
  return <ProxySettings />          
}



export default ProxySettingsTab
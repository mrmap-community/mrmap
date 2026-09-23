import { useMemo } from 'react';
import { ResourceContext, useRecordContext, useResourceContext } from 'react-admin';
import { RelatedResource } from '../../../../../providers/dataProvider';
import ListWebMapServiceUpdateSetting from '../../../Update/Wms/ListWebMapServiceUpdateSetting';


export const UpdateSettingTab = () => {

  const resource = useResourceContext()
  const record = useRecordContext()

  const relatedResource = useMemo<RelatedResource | undefined>(()=>{
    if (resource !== undefined && record !== undefined){
      return {resource, id: record.id}
    }
  },[resource, record])

  return (
      <ResourceContext
        value='WebMapServiceUpdateSetting'
      >
        <ListWebMapServiceUpdateSetting
          relatedResource={relatedResource}
        />
      </ResourceContext>

  )
}

export default UpdateSettingTab
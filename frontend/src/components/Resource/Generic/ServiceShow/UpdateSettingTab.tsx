import { useMemo } from 'react';
import { ResourceContext, useRecordContext, useResourceContext } from 'react-admin';

import { RelatedResource } from '../../../../providers/dataProvider';
import ListUpdateSetting from '../Update/ListUpdateSetting';



export const UpdateSettingTab = (
  {
    resource,
  }: {
    resource: string
  }
) => {

  const relatedResourceContextValue = useResourceContext()
  const record = useRecordContext()

  const relatedResource = useMemo<RelatedResource | undefined>(()=>{
    if (relatedResourceContextValue !== undefined && record !== undefined){
      return {resource: relatedResourceContextValue, id: record.id}
    }
  },[relatedResourceContextValue, record])

  return (
      <ResourceContext
        value={resource}
      >
        <ListUpdateSetting
          relatedResource={relatedResource}
        />
      </ResourceContext>

  )
}

export default UpdateSettingTab
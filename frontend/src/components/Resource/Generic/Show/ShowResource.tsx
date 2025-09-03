import { ReactNode, useMemo } from 'react';
import { RecordRepresentation, Show, ShowProps, ShowViewProps, useResourceContext, WithRecord } from 'react-admin';
import JsonApiReferenceField from '../../../../jsonapi/components/ReferenceField';
import SimpleCard from '../../../MUI/SimpleCard';


export interface ShowResourceProps extends Partial<ShowViewProps>{
  subheader?: ReactNode
  showProps?: ShowProps
  sources?: string[]
}

const ShowResource = ({
  showProps,
  sources=["id", "created_at", "created_by", "last_modified_at", "last_modified_by", "string_representation"],
  ...rest
}: ShowResourceProps) => {
  const resource = useResourceContext({resource: rest?.resource})
    
  const meta = useMemo(()=>{
    const meta = {
      jsonApiParams: {} as any
    }
    meta["jsonApiParams"][`fields[${resource}]`] = sources.join(",")
    return meta
  },[]) 
  


  const defaultSubheader = useMemo(() => {
    return (
      <>
        <WithRecord label="createdAt" render={record => <span>Created on {record.createdAt}</span>} />
        <WithRecord label='createdBy' render={record => <span> by {<JsonApiReferenceField source='createdBy' reference='User'/>}</span>} />
        <WithRecord label="changedAt" render={record => <span> · Updated on {record.lastModifiedAt}</span>} />
        <WithRecord label='createdBy' render={record => <span> by {<JsonApiReferenceField source='lastModifiedBy' reference='User'/>}</span>} />
      </>

    )
  },[]);
  // TODO: set sparsefields...
  return (
    <Show
      queryOptions={{meta: meta}}
      {...showProps}
    >
      <SimpleCard
        title={rest.title ?? <RecordRepresentation />} 
        subheader={rest.subheader ?? defaultSubheader}
      >
        {rest.children}
      </SimpleCard>
    </Show>
  )
};


export default ShowResource;
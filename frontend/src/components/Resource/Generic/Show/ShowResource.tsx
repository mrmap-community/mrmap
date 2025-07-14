import { ReactNode, useMemo } from 'react';
import { RecordRepresentation, Show, ShowViewProps, WithRecord } from 'react-admin';
import JsonApiReferenceField from '../../../../jsonapi/components/ReferenceField';
import SimpleCard from '../../../MUI/SimpleCard';


export interface ShowResourceProps extends Partial<ShowViewProps> {
  subheader?: ReactNode
}

const ShowResource = ({
  ...rest
}: ShowResourceProps) => {
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

  return (
    <Show>
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
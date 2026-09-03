import { useRecordContext } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import EditDialogButton from '../../Dialog/EditDialogButton';


export const WebMapServiceOperationUrlsTab = () => {
  const record = useRecordContext();
  return (
      <ListGuesser 
        resource='WebMapServiceOperationUrl'
        relatedResource='WebMapService'
        relatedResourceId={record?.id}
        rowActions={<EditDialogButton editDialogProps={{resource: 'WebMapServiceOperationUrl'}}/>}
      />
  )
}

export default WebMapServiceOperationUrlsTab
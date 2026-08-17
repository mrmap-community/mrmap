import { ShowViewProps } from 'react-admin';
import SimpleList from '../../Generic/List/SimpleList';

export interface RecordsProps extends Partial<ShowViewProps> {

}

const Records = ({
  
  ...rest
}: RecordsProps) => {

  return (
    <div>
      <SimpleList 
        resource='DatasetMetadataRecord'
        relatedResource='CatalogueService'
      />
      <SimpleList 
        resource='ServiceMetadataRecord'
        relatedResource='CatalogueService'
      />
    </div>
  )
};


export default Records;
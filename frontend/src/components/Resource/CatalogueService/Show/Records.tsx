import { ShowViewProps } from 'react-admin';
import SimpleList from '../../Generic/List/SimpleList';

export interface RecordsProps extends Partial<ShowViewProps> {

}

const Records = ({
  
  ...rest
}: RecordsProps) => {

  return (
    <>
      <SimpleList 
        resource='DatasetMetadataRecord'
        relatedResource='CatalogueService'
      />
      <SimpleList 
        resource='ServiceMetadataRecord'
        relatedResource='CatalogueService'
      />
    </>
  )
};


export default Records;
import { ShowViewProps } from 'react-admin';
import { Fragment } from 'react/jsx-runtime';
import SimpleList from '../../Generic/List/SimpleList';

export interface RecordsProps extends Partial<ShowViewProps> {

}

const Records = ({
  
  ...rest
}: RecordsProps) => {

  return (
    <Fragment>
      <SimpleList 
        resource='DatasetMetadataRecord'
        relatedResource='CatalogueService'
      />
      <SimpleList 
        resource='ServiceMetadataRecord'
        relatedResource='CatalogueService'
      />
    </Fragment>
  )
};


export default Records;
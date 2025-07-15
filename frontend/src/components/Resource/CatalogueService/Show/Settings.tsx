import { ShowViewProps } from 'react-admin';
import SimpleList from '../../Generic/List/SimpleList';

export interface SettingsProps extends Partial<ShowViewProps> {

}

const Settings = ({
  
  ...rest
}: SettingsProps) => {

  return (
    <SimpleList 
      resource='CatalogueServiceOperationUrl'
      relatedResource='CatalogueService'
    />
  )
};


export default Settings;
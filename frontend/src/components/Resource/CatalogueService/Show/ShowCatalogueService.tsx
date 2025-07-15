import { ShowViewProps } from 'react-admin';
import SimpleTabs from '../../../MUI/SimpleTabs';
import HistoryList from '../../Generic/History/HistoryList';
import ShowResource from '../../Generic/Show/ShowResource';
import Overview from './Overview';
import Records from './Records';
import Settings from './Settings';

export interface ShowCatalogueServiceProps extends Partial<ShowViewProps> {

}

const ShowCatalogueService = ({
  
  ...rest
}: ShowCatalogueServiceProps) => {

  return (
    <ShowResource>
      <SimpleTabs 
        tabs={[
          {label: 'Overview', children: <Overview/>},
          {label: 'Changelog', children: <HistoryList/>},
          {label: 'Records', children: <Records/>},
          {label: 'Settings', children: <Settings/>},
        ]}
      />
    </ShowResource>
  )
};


export default ShowCatalogueService;
import { ShowViewProps } from 'react-admin';
import SimpleTabs from '../../../MUI/SimpleTabs';
import HistoryList from '../../Generic/History/HistoryList';
import ShowResource from '../../Generic/Show/ShowResource';
import Overview from './Overview';
import Records from './Records';
import Settings from './Settings';

export interface ShowCatalogueServiceProps extends Partial<ShowViewProps> {

}

const sources = ["id", "title", "abstract"]

const ShowCatalogueService = ({
  
  ...rest
}: ShowCatalogueServiceProps) => {


  return (
    <ShowResource
      sources={["id", "title", "abstract", "created_at", "created_by", "last_modified_at", "last_modified_by", "string_representation"]}
    >
      <SimpleTabs 
        tabs={[
          {label: 'Overview', children: <Overview sources={sources}/>},
          {label: 'Changelog', children: <HistoryList/>},
          {label: 'Records', children: <Records/>},
          {label: 'Settings', children: <Settings/>},
        ]}
      />
    </ShowResource>
  )
};


export default ShowCatalogueService;
import { ResourceContext } from 'react-admin';
import ListWebMapServiceUpdateSetting from '../../../Update/Wms/ListWebMapServiceUpdateSetting';


export const UpdateSettingTab = () => {
  return (
    <ResourceContext
      value='WebMapServiceUpdateSetting'
    >
      <ListWebMapServiceUpdateSetting/>
    </ResourceContext>
  )
}

export default UpdateSettingTab
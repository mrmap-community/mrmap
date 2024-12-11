import {
  ResourceProps
} from 'react-admin';

import AgricultureIcon from '@mui/icons-material/Agriculture';
import CorporateFareIcon from '@mui/icons-material/CorporateFare';
import DatasetIcon from '@mui/icons-material/Dataset';
import LayersIcon from '@mui/icons-material/Layers';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import MapIcon from '@mui/icons-material/Map';
import NotListedLocationIcon from '@mui/icons-material/NotListedLocation';
import CustomerIcon from '@mui/icons-material/Person';
import PlagiarismIcon from '@mui/icons-material/Plagiarism';
import TravelExploreIcon from '@mui/icons-material/TravelExplore';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import CatalogueServiceList from '../Lists/CatalogueServiceList';
import WmsList from '../Lists/WmsList';
import CreateAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/CreateAllowedWebMapServiceOperation';
import EditAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/EditAllowedWebMapServiceOperation';
import { WmsShow } from './WebMapService/WmsShow';

import MultipleStopIcon from '@mui/icons-material/MultipleStop';
import ListBackgroundProcess from './BackgroundProcess/ListBackgroundProcess';
import ShowBackgroundProcess from './BackgroundProcess/ShowBackgroundProcess';
import CreateWebMapServiceMonitoringSetting from './Monitoring/Wms/CreateWebMapServiceMonitoringSetting';
import EditWebMapServiceMonitoringSetting from './Monitoring/Wms/EditWebMapServiceMonitoringSetting';

const RESOURCES: Array<ResourceProps> = [
  {name: "WebMapService", icon: MapIcon, list: WmsList, show: WmsShow},
  {name: "HistoricalWebMapService"},
  
  {name: "Layer", icon: LayersIcon},
  {name: "WebFeatureService", icon: TravelExploreIcon},
  {name: "FeatureType", icon: NotListedLocationIcon},
  {name: "CatalogueService", icon: PlagiarismIcon, list: CatalogueServiceList},
  {name: "HarvestingJob", icon: AgricultureIcon},

  {name: "Keyword", icon: LocalOfferIcon},
  {name: "DatasetMetadataRecord", icon: DatasetIcon},
  {name: "ServiceMetadataRecord", icon: DatasetIcon},

  // monitoring
  {
    name: "WebMapServiceMonitoringSetting", 
    create: CreateWebMapServiceMonitoringSetting,
    edit: EditWebMapServiceMonitoringSetting,
  },
  {name: "GetCapabilitiesProbe"},
  {name: "GetMapProbe"},
  

  {name: "WebMapServiceMonitoringRun"},
  {name: "GetCapabilitiesProbeResult"},
  {name: "GetMapProbeResult"},

  {name: "ReferenceSystem"},


  {name: "CrontabSchedule"},
  {name: "BackgroundProcess", list: ListBackgroundProcess, show: ShowBackgroundProcess},

  {name: "AllowedWebMapServiceOperation", icon: VpnLockIcon, create: CreateAllowedWebMapServiceOperation, edit: EditAllowedWebMapServiceOperation},
  {name: "WebMapServiceProxySetting", icon: MultipleStopIcon},
  
  {name: "User", icon: CustomerIcon},
  {name: "Organization", icon: CorporateFareIcon },
  {name: "Group", icon: CorporateFareIcon },
];

export default RESOURCES;
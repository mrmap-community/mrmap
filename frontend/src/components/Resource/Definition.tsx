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
import WmsList from '../Lists/WmsList';
import CreateAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/CreateAllowedWebMapServiceOperation';
import EditAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/EditAllowedWebMapServiceOperation';
import CatalogueServiceList from './CatalogueService/CatalogueServiceList';
import { WmsShow } from './WebMapService/WmsShow';

import HttpIcon from '@mui/icons-material/Http';
import MultipleStopIcon from '@mui/icons-material/MultipleStop';
import UpdateIcon from '@mui/icons-material/Update';
import ListBackgroundProcess from './BackgroundProcess/ListBackgroundProcess';
import ShowBackgroundProcess from './BackgroundProcess/ShowBackgroundProcess';
import ShowCatalogueService from './CatalogueService/Show/ShowCatalogueService';
import ShowDatasetMetadataRecord from './DatasetMetadataRecord/ShowDatasetMetadataRecord';
import ShowHarvestingJob from './HarvestingJob/ShowHarvestingJob';
import CreateWebMapServiceMonitoringSetting from './Monitoring/Wms/CreateWebMapServiceMonitoringSetting';
import EditWebMapServiceMonitoringSetting from './Monitoring/Wms/EditWebMapServiceMonitoringSetting';

const RESOURCES: Array<ResourceProps> = [
  {name: "WebMapService", icon: MapIcon, list: WmsList, show: WmsShow},
  {name: "WebMapServiceProxySetting", icon: MultipleStopIcon},
  {name: "WebMapServiceOperationUrl", icon: HttpIcon},

  {name: "HistoricalWebMapService"},
  
  {name: "Layer", icon: LayersIcon},
  {name: "WebFeatureService", icon: TravelExploreIcon},
  {name: "FeatureType", icon: NotListedLocationIcon},
  
  
  {name: "CatalogueService", icon: PlagiarismIcon, show: ShowCatalogueService, list: CatalogueServiceList},
  {name: "CatalogueServiceOperationUrl", icon: HttpIcon},

  
  
  {name: "HarvestingJob", icon: AgricultureIcon, show: ShowHarvestingJob},
  {name: "TemporaryMdMetadataFile"},
  {name: "HarvestingLog"},
  {name: "PeriodicHarvestingJob", icon: UpdateIcon },


  {name: "Keyword", icon: LocalOfferIcon},
  {name: "DatasetMetadataRecord", icon: DatasetIcon, show: ShowDatasetMetadataRecord},
  {name: "ServiceMetadataRecord", icon: DatasetIcon},
  {name: "HarvestedMetadataRelation", icon: DatasetIcon},


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


  {name: "CrontabSchedule",},
  {name: "TaskResult"},
  {name: "BackgroundProcess", list: ListBackgroundProcess, show: ShowBackgroundProcess},
  {name: "BackgroundProcessLog", },

  {name: "AllowedWebMapServiceOperation", icon: VpnLockIcon, create: CreateAllowedWebMapServiceOperation, edit: EditAllowedWebMapServiceOperation},
  
  {name: "User", icon: CustomerIcon},
  {name: "Organization", icon: CorporateFareIcon },
  {name: "Group", icon: CorporateFareIcon },


  // Changelogs
  {name: "HistoryWebMapService"},


  // System
  {name: "CrontabSchedule"},
  {name: "PeriodicTask"},
];

export default RESOURCES;
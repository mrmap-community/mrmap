import SyncAltIcon from '@mui/icons-material/SyncAlt';
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

import ContactsIcon from '@mui/icons-material/Contacts';
import HttpIcon from '@mui/icons-material/Http';
import LegendToggleIcon from '@mui/icons-material/LegendToggle';
import MultipleStopIcon from '@mui/icons-material/MultipleStop';
import UpdateIcon from '@mui/icons-material/Update';
import ListAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation';
import ListBackgroundProcess from './BackgroundProcess/ListBackgroundProcess';
import ShowBackgroundProcess from './BackgroundProcess/ShowBackgroundProcess';
import ShowCatalogueService from './CatalogueService/Show/ShowCatalogueService';
import ShowDatasetMetadataRecord from './DatasetMetadataRecord/ShowDatasetMetadataRecord';
import ShowHarvestingJob from './HarvestingJob/ShowHarvestingJob';
import CreateWebMapServiceMonitoringSetting from './Monitoring/Wms/CreateWebMapServiceMonitoringSetting';
import EditWebMapServiceMonitoringSetting from './Monitoring/Wms/EditWebMapServiceMonitoringSetting';
import ListPeriodicHarvestingJob from './PeriodicHarvestingJob/ListPeriodicHarvestingJob';
import { ShowWebMapServiceUpdate } from './WebMapServiceUpdateJob/ShowWebMapServiceUpdateJob';

const RESOURCES: Array<ResourceProps> = [
  {name: "WebMapService", icon: MapIcon, list: WmsList, show: WmsShow, options: { menu: { group: "WMS", order: 10 } }},
  {name: "WebMapServiceProxySetting", icon: MultipleStopIcon, options: { menu: { group: "WMS", order: 30 } }},
  {name: "WebMapServiceOperationUrl", icon: HttpIcon},
  {name: "HistoricalWebMapService"},
  {name: "Layer", icon: LayersIcon, options: { menu: { group: "WMS", order: 20 } }},
  
  
  {name: "WebFeatureService", icon: TravelExploreIcon, options: { menu: { group: "WFS", order: 10 } }},
  {name: "WebFeatureServiceProxySetting", icon: MultipleStopIcon, options: { menu: { group: "WFS", order: 20 } }},
  {name: "FeatureType", icon: NotListedLocationIcon, options: { menu: { group: "WFS", order: 30 } }},
  
  
  {name: "CatalogueService", icon: PlagiarismIcon, show: ShowCatalogueService, list: CatalogueServiceList, options: { menu: { group: "CSW", order: 10 } }},
  {name: "CatalogueServiceOperationUrl", icon: HttpIcon},

  {name: "HarvestingJob", icon: AgricultureIcon, show: ShowHarvestingJob, options: { menu: { group: "CSW", order: 20 } }},
  {name: "TemporaryMdMetadataFile"},
  {name: "HarvestingLog"},
  {name: "PeriodicHarvestingJob", icon: UpdateIcon, list: ListPeriodicHarvestingJob },

  {name: "MetadataContact", icon: ContactsIcon},
  {name: "Keyword", icon: LocalOfferIcon, options: { menu: { group: "Metadata", order: 30 } }},
  {name: "DatasetMetadataRecord", icon: DatasetIcon, show: ShowDatasetMetadataRecord, options: { menu: { group: "Metadata", order: 10 } }},
  {name: "ServiceMetadataRecord", icon: DatasetIcon, options: { menu: { group: "Metadata", order: 20 } }},
  {name: "HarvestedMetadataRelation", icon: DatasetIcon},


  // update
  {name: "WebMapServiceUpdateJob", icon: UpdateIcon, show: ShowWebMapServiceUpdate, options: { menu: { group: "WMS", order: 40 } }},
  {name: "LayerMapping", icon: SyncAltIcon},

  // monitoring
  {
    name: "WebMapServiceMonitoringSetting", 
    icon: LegendToggleIcon,
    create: CreateWebMapServiceMonitoringSetting,
    edit: EditWebMapServiceMonitoringSetting,
    options: { menu: { group: "WMS", order: 50 } }
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


  // security proxy
  {
    name: "AllowedWebMapServiceOperation", 
    icon: VpnLockIcon, 
    create: CreateAllowedWebMapServiceOperation, 
    edit: EditAllowedWebMapServiceOperation,
    list: ListAllowedWebMapServiceOperation,
    options: { menu: { group: "WMS", order: 50 } }
    
  },
  {name: "WebMapServiceOperation",},
  {name: "AllowedWebFeatureServiceOperation", icon: VpnLockIcon, options: { menu: { group: "WFS", order: 40 } }},
  {name: "WebFeatureServiceOperation",},

  {name: "User", icon: CustomerIcon, options: { menu: { group: "Accounts", order: 10 } }},
  {name: "Organization", icon: CorporateFareIcon, options: { menu: { group: "Accounts", order: 20 } }},
  {name: "Group", icon: CorporateFareIcon },


  // Changelogs
  {name: "HistoryWebMapService"},


  // System
  {name: "SystemInfo", options: { menu: { group: "Admin", order: 10 } }},
  {name: "CrontabSchedule"},
  {name: "PeriodicTask", options: { menu: { group: "Admin", order: 20 }}},
];

export default RESOURCES;
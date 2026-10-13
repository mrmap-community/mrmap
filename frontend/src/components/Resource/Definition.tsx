import SyncAltIcon from '@mui/icons-material/SyncAlt';
import {
  ResourceProps
} from 'react-admin';

import AgricultureIcon from '@mui/icons-material/Agriculture';
import ContactsIcon from '@mui/icons-material/Contacts';
import CorporateFareIcon from '@mui/icons-material/CorporateFare';
import DatasetIcon from '@mui/icons-material/Dataset';
import HttpIcon from '@mui/icons-material/Http';
import LayersIcon from '@mui/icons-material/Layers';
import LegendToggleIcon from '@mui/icons-material/LegendToggle';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import MapIcon from '@mui/icons-material/Map';
import MultipleStopIcon from '@mui/icons-material/MultipleStop';
import NotListedLocationIcon from '@mui/icons-material/NotListedLocation';
import CustomerIcon from '@mui/icons-material/Person';
import PlagiarismIcon from '@mui/icons-material/Plagiarism';
import TravelExploreIcon from '@mui/icons-material/TravelExplore';
import UpdateIcon from '@mui/icons-material/Update';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import ListAllowedWebMapServiceOperation from './AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation';
import ListBackgroundProcess from './BackgroundProcess/ListBackgroundProcess';
import AbortBackgroundProcessButton from './BackgroundProcess/AbortBackgroundProcessButton';
import ShowBackgroundProcess from './BackgroundProcess/ShowBackgroundProcess';
import CatalogueServiceList from './CatalogueService/CatalogueServiceList';
import ShowCatalogueService from './CatalogueService/Show/ShowCatalogueService';
import ListDatasetMetadataRecord from './DatasetMetadataRecord/ListDatasetMetadataRecord';
import ListServiceMetadataRecord from './ServiceMetadataRecord/ListServiceMetadataRecord';
import ShowDatasetMetadataRecord from './DatasetMetadataRecord/ShowDatasetMetadataRecord';
import ShowHarvestingJob from './HarvestingJob/ShowHarvestingJob';
import ShowWebMapServiceMonitoringRun from './Monitoring/ShowWebMapServiceMonitoringRun';
import ShowWebFeatureServiceMonitoringRun from './Monitoring/ShowWebFeatureServiceMonitoringRun';
import ShowCatalogueServiceMonitoringRun from './Monitoring/ShowCatalogueServiceMonitoringRun';
import ListWebMapServiceMonitoringSetting from './Monitoring/WebMapServiceMonitoringSetting/ListWebMapServiceMonitoringSetting';
import ListWebFeatureServiceMonitoringSetting from './Monitoring/WebFeatureServiceMonitoringSetting/ListWebFeatureServiceMonitoringSetting';
import ListCatalogueServiceMonitoringSetting from './Monitoring/CatalogueServiceMonitoringSetting/ListCatalogueServiceMonitoringSetting';
import ListPeriodicHarvestingJob from './PeriodicHarvestingJob/ListPeriodicHarvestingJob';
import ListSystemInfo from './System/ListSystemInfo';
import WfsShow from './WebFeatureService/Show/WfsShow';
import WmsViewerButtons from './WebMapService/Button/ListActions';
import { WmsShow } from './WebMapService/Show/WmsShow';
import ShowWebFeatureServiceUpdateJob from './WebFeatureServiceUpdateJob/ShowWebFeatureServiceUpdateJob';
import { ShowWebMapServiceUpdate } from './WebMapServiceUpdateJob/ShowWebMapServiceUpdateJob';


const RESOURCES: Array<ResourceProps> = [
  {
    name: "WebMapService", 
    icon: MapIcon, 
    show: WmsShow, 
    options: { 
      menu: { group: "WMS", order: 10 },
      list: { 
        perPage: 25,
        sort: { field: 'title', order: 'ASC' },
        defaultSelectedColumns: ["id", "title", "abstract", "username", "actions", ],
        sparseFieldsets: [{type: "WebMapService", fields: ["isSecured", "xmlBackupFileSecured"]}],
        additionalActions: WmsViewerButtons
      }
    }
  },
  {name: "WebMapServiceProxySetting", icon: MultipleStopIcon, },
  {name: "WebMapServiceOperationUrl", icon: HttpIcon},
  {name: "HistoricalWebMapService"},
  {name: "Layer", icon: LayersIcon, options: { menu: { group: "WMS", order: 20 } }},
  
  
  {name: "WebFeatureService", show: WfsShow, icon: TravelExploreIcon, options: { menu: { group: "WFS", order: 10 } }},
  {name: "WebFeatureServiceProxySetting", icon: MultipleStopIcon},
  {name: "FeatureType", icon: NotListedLocationIcon, options: { menu: { group: "WFS", order: 30 } }},
  
  
  {
    name: "CatalogueService", 
    icon: PlagiarismIcon, 
    show: ShowCatalogueService, 
    list: CatalogueServiceList, 
    options: { 
      menu: { group: "CSW", order: 10 },
      list: {
        sparseFieldsets: [{type: 'CatalogueService', fields: ['runningHarvestingJob']}]
      }
    }
  },
  {name: "CatalogueServiceOperationUrl", icon: HttpIcon},

  {name: "HarvestingJob", icon: AgricultureIcon, show: ShowHarvestingJob, options: { menu: { group: "CSW", order: 20 } }},
  {name: "TemporaryMdMetadataFile"},
  {name: "HarvestingLog"},
  {name: "PeriodicHarvestingJob", icon: UpdateIcon, list: ListPeriodicHarvestingJob },

  {name: "MetadataContact", icon: ContactsIcon},
  {name: "Keyword", icon: LocalOfferIcon, options: { menu: { group: "Metadata", order: 30 } }},
  {name: "DatasetMetadataRecord", icon: DatasetIcon, list: ListDatasetMetadataRecord, show: ShowDatasetMetadataRecord, options: { menu: { group: "Metadata", order: 10 } }},
  {name: "ServiceMetadataRecord", icon: DatasetIcon, list: ListServiceMetadataRecord, options: { menu: { group: "Metadata", order: 20 } }},
  {name: "HarvestedMetadataRelation", icon: DatasetIcon},


  // update
  {name: "WebMapServiceUpdateSetting", icon: UpdateIcon},
  {name: "WebMapServiceUpdateJob", icon: UpdateIcon, show: ShowWebMapServiceUpdate, options: { menu: { group: "WMS", order: 40 } }},
  {name: "LayerMapping", icon: SyncAltIcon},

  {name: "FeatureTypeMapping", icon: SyncAltIcon},
  {name: "WebFeatureServiceUpdateSetting", icon: UpdateIcon},
  {name: "WebFeatureServiceUpdateJob", icon: UpdateIcon, show: ShowWebFeatureServiceUpdateJob, options: { menu: { group: "WFS", order: 40 } }},
  

  {name: "CatalogueServiceUpdateSetting", icon: UpdateIcon},
  {name: "CatalogueServiceUpdateJob", icon: UpdateIcon, options: { menu: { group: "CSW", order: 40 } }},
  

  // monitoring
  {
    name: "WebMapServiceMonitoringSetting", 
    icon: LegendToggleIcon,
    list: ListWebMapServiceMonitoringSetting,
    //create: CreateWebMapServiceMonitoringSetting,
    //edit: EditWebMapServiceMonitoringSetting,
    options: { menu: { group: "WMS", order: 50 } }
  },
  {name: "GetCapabilitiesProbe"},
  {name: "GetMapProbe"},
  

  {name: "WebMapServiceMonitoringRun", show: ShowWebMapServiceMonitoringRun},
  {name: "GetCapabilitiesProbeResult"},
  {name: "GetMapProbeResult"},


  {
    name: "WebFeatureServiceMonitoringSetting",
    icon: LegendToggleIcon,
    list: ListWebFeatureServiceMonitoringSetting,
    options: { menu: { group: "WFS", order: 50 } }
  },
  {name: "WebFeatureServiceGetCapabilitiesProbe"},
  {name: "WebFeatureServiceGetFeatureProbe"},
  {
    name: "WebFeatureServiceMonitoringRun",
    show: ShowWebFeatureServiceMonitoringRun
  },
  {name: "WebFeatureServiceGetCapabilitiesProbeResult"},
  {name: "WebFeatureServiceGetFeatureProbeResult"},

  {
    name: "CatalogueServiceMonitoringSetting",
    icon: LegendToggleIcon,
    list: ListCatalogueServiceMonitoringSetting,
    options: { menu: { group: "CSW", order: 50 } }
  },
  {name: "CatalogueServiceGetCapabilitiesProbe"},
  {name: "CatalogueServiceGetRecordsProbe"},
  {
    name: "CatalogueServiceMonitoringRun",
    show: ShowCatalogueServiceMonitoringRun
  },
  {name: "CatalogueServiceGetCapabilitiesProbeResult"},
  {name: "CatalogueServiceGetRecordsProbeResult"},



  {name: "ReferenceSystem"},

  {name: "TaskResult"},
  {
    name: "BackgroundProcess",
    icon: UpdateIcon,
    list: ListBackgroundProcess,
    show: ShowBackgroundProcess,
    options: {
      menu: { group: "Admin", order: 30 },
      list: { additionalActions: AbortBackgroundProcessButton }
    }
  },
  {name: "BackgroundProcessLog", },


  // security proxy
  {
    name: "AllowedWebMapServiceOperation", 
    icon: VpnLockIcon, 
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
  {
    name: "SystemInfo", 
    list: ListSystemInfo, 
    options: { menu: { group: "Admin", order: 10 } }
  },
  {name: "CrontabSchedule",},
  {name: "PeriodicTask", options: { menu: { group: "Admin", order: 20 }}},
];

export default RESOURCES;
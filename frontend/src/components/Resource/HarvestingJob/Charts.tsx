import { ChartsLegend, ChartsTooltip, ResponsiveChartContainer } from "@mui/x-charts";
import {
  mangoFusionPalette
} from '@mui/x-charts/colorPalettes';
import { PiePlot } from '@mui/x-charts/PieChart';
import { useCallback, useMemo } from "react";
import { useCreatePath, useRecordContext, useResourceDefinition } from "react-admin";
import { useNavigate } from 'react-router-dom';



const HarvestResultPieChart = () => {
  const createPath = useCreatePath();
  const record = useRecordContext();
  const { name } = useResourceDefinition()
  const basePath = useMemo(()=> name && createPath({ resource: name, type: 'show', id: record?.id }), [name, record])
  const navigate = useNavigate();

  const data = useMemo(() => {
    const total = record?.totalRecords

    const handledDatasetRecords = record?.newDatasetMetadataCount + record?.existingDatasetMetadataCount + record?.updatedDatasetMetadataCount + record?.duplicatedDatasetMetadataCount
    const handledServiceRecords = record?.newServiceMetadataCount + record?.existingServiceMetadataCount + record?.updatedServiceMetadataCount + record?.duplicatedServiceMetadataCount
    const unhandledRecords = total - handledDatasetRecords - handledServiceRecords

    return [
      ...unhandledRecords >0 ? [{ id:'u_r', name: 'Unhandled Records', value: unhandledRecords, color: "unhandled" }]: [],
      ...record?.newDatasetMetadataCount > 0 ? [{ 
        id:'n_d', 
        label: 'New Datasets',
        href: `${basePath}/HarvestedDatasetMetadataRelation?filter=${JSON.stringify({collecting_state: 'new'})}`,
        value: record?.newDatasetMetadataCount, 
      }]: [],
      ...record?.existingDatasetMetadataCount > 0 ? [{ 
        id:'e_d',
        label: 'Existing Datasets',
        href: `${basePath}/HarvestedDatasetMetadataRelation?filter=${JSON.stringify({collecting_state: 'existing'})}`,
        value: record?.existingDatasetMetadataCount, 
      }]: [],
      ...record?.updatedDatasetMetadataCount > 0 ? [{ 
        id:'u_d', 
        label: 'Updated Datasets',
        href: `${basePath}/HarvestedDatasetMetadataRelation?filter=${JSON.stringify({collecting_state: 'updated'})}`,
        value: record?.updatedDatasetMetadataCount, 
      }]: [],
      ...record?.duplicatedDatasetMetadataCount > 0 ? [{ 
        id:'e_d',
        label: 'Duplicated Datasets',
        href: `${basePath}/HarvestedDatasetMetadataRelation?filter=${JSON.stringify({collecting_state: 'duplicated'})}`,
        value: record?.duplicatedDatasetMetadataCount, 
      }]: [],
      ...record?.newServiceMetadataCount > 0 ? [{ 
        id:'n_s',
        label: 'New Services',
        href: `${basePath}/HarvestedServiceMetadataRelation?filter=${JSON.stringify({collecting_state: 'new'})}`,
        value: record?.newServiceMetadataCount, 
      }]: [],
      ...record?.existingServiceMetadataCount > 0 ? [{ 
        id:'e_s',
        label: 'Existing Services',
        href: `${basePath}/HarvestedServiceMetadataRelation?filter=${JSON.stringify({collecting_state: 'existing'})}`,
        value: record?.existingServiceMetadataCount, 
      }]: [],
      ...record?.updatedServiceMetadataCount > 0 ? [{ 
        id:'u_s',
        label: 'Updated Services',
        href: `${basePath}/HarvestedServiceMetadataRelation?filter=${JSON.stringify({collecting_state: 'updated'})}`,
        value: record?.updatedServiceMetadataCount, 
      }]: [],
      ...record?.duplicatedServiceMetadataCount > 0 ? [{ 
        id:'e_d',
        label: 'Duplicated Services',
        href: `${basePath}/HarvestedServiceMetadataRelation?filter=${JSON.stringify({collecting_state: 'duplicated'})}`,
        value: record?.duplicatedServiceMetadataCount, 
      }]: [],
  ]
  }, [record])



  const navigatePreFilteredList = useCallback((dataItem: any)=>{
    dataItem.href !== undefined && navigate(dataItem.href)
  },[])

  return (
    <ResponsiveChartContainer
      series={[
        {
          type: 'pie',
          data: data,
          highlightScope: { fade: 'global', highlight: 'item' },
          faded: { innerRadius: 30, additionalRadius: -30, color: 'gray'},
          arcLabel: (item) => `${item.value}`,
          arcLabelMinAngle: 50,
          paddingAngle: 0.5,
          cornerRadius: 5,
        },
      ]}
      colors={mangoFusionPalette}
      height={400}
      margin={{bottom: 100, left: 100, right:100}}
    >
      <PiePlot
        onItemClick={(event, d) => navigatePreFilteredList(data[d.dataIndex])}
      />
      <ChartsTooltip 
        trigger="item"
      />
      <ChartsLegend 
        direction="row" 
        position={{horizontal: 'middle', vertical: 'bottom'}} 
        onItemClick={(event, d) => navigatePreFilteredList(data.find(r => r.id === d.itemId))}
      />
    </ResponsiveChartContainer>
  )

}


export default HarvestResultPieChart;
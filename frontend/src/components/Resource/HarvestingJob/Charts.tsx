import { useTheme } from "@mui/material";
import { useMemo, useState } from "react";
import { RaRecord, useTheme as useRaTheme, useRecordContext } from "react-admin";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';



const HarvestResultPieChart = () => {
  const theme = useTheme();
  const [currentTheme, _] = useRaTheme();
  const [activeIndex, setActiveIndex] = useState<number>()

  const record = useRecordContext();

  const colors: {[index: string]: string} = useMemo(()=>({
    "new": currentTheme === 'dark' ? theme.palette.primary.dark: theme.palette.primary.light,
    "existing": currentTheme === 'dark' ? theme.palette.secondary.dark: theme.palette.secondary.light,
    "updated": currentTheme === 'dark' ? theme.palette.success.dark: theme.palette.success.light,
    "duplicated": currentTheme === 'dark' ? theme.palette.warning.dark: theme.palette.warning.light,
    "unhandled": currentTheme === 'dark' ? theme.palette.error.dark: theme.palette.error.light,
  }), [currentTheme])

  const data = useMemo(() => {
    const total = record?.totalRecords

    const datasetRecords = {
      "new": [] as RaRecord[],
      "existing": [] as RaRecord[],
      "updated": [] as RaRecord[],
      "duplicated": [] as RaRecord[],
    }
    
    record?.harvestedDatasetMetadata?.forEach((record: RaRecord) => {
      switch(record.collectingState){
        case "new":
          datasetRecords.new.push(record);
          break;
        case "existing":
          datasetRecords.existing.push(record);
          break;
        case "updated":
          datasetRecords.updated.push(record);
          break;
        case "duplicated":
          datasetRecords.duplicated.push(record);
          break;
      }
    })

    const serviceRecords = {
      "new": [] as RaRecord[],
      "existing": [] as RaRecord[],
      "updated": [] as RaRecord[],
      "duplicated": [] as RaRecord[],
    }

    record?.harvestedServiceMetadata?.forEach((record: RaRecord) => {
      switch(record.collectingState){
        case "new":
          serviceRecords.new.push(record);
          break;
        case "existing":
          serviceRecords.existing.push(record);
          break;
        case "updated":
          serviceRecords.updated.push(record);
          break;
        case "duplicated":
          serviceRecords.duplicated.push(record);
          break;
      }
    })

    console.log(datasetRecords, serviceRecords)
    const handledDatasetRecords = datasetRecords.new.length + datasetRecords.existing.length + datasetRecords.updated.length + datasetRecords.duplicated.length
    const handledServiceRecords = serviceRecords.new.length + serviceRecords.existing.length + serviceRecords.updated.length + serviceRecords.duplicated.length
    const unhandledRecords = total - handledDatasetRecords - handledServiceRecords

    return [
      ...unhandledRecords >0 ? [{ id:'u_r', name: 'Unhandled Records', value: unhandledRecords, color: "unhandled" }]: [],
      ...datasetRecords.new.length > 0 ? [{ id:'n_d', name: 'New Datasets', value: datasetRecords.new.length, color: "new" }]: [],
      ...datasetRecords.existing.length > 0 ? [{ id:'e_d', name: 'Existing Datasets', value: datasetRecords.existing.length, color: "existing" }]: [],
      ...datasetRecords.updated.length > 0 ? [{ id:'u_d', name: 'Updated Datasets', value: datasetRecords.updated.length, color: "updated" }]: [],
      ...datasetRecords.duplicated.length > 0 ? [{ id:'e_d', name: 'Duplicated Datasets', value: datasetRecords.duplicated.length, color: "duplicated" }]: [],

      ...serviceRecords.new.length > 0 ? [{ id:'n_s', name: 'New Services', value: serviceRecords.new.length, color: "new" }]: [],
      ...serviceRecords.existing.length > 0 ? [{ id:'e_s', name: 'Existing Services', value: serviceRecords.existing.length, color: "existing" }]: [],
      ...serviceRecords.updated.length > 0 ? [{ id:'u_s', name: 'Updated Services', value: serviceRecords.updated.length, color: "updated" }]: [],
      ...serviceRecords.duplicated.length > 0 ? [{ id:'e_d', name: 'Duplicated Services', value: serviceRecords.duplicated.length, color: "duplicated" }]: [],

  ]
  }, [record])

  const cells = useMemo(() => data.map((entry, index) => (
      <Cell key={`cell-${entry.id}`} fill={colors[entry.color]} opacity={activeIndex === -1 || index === activeIndex ? 1 : 0.5}/>
  )), [data, activeIndex])
  

  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={200} >
        <PieChart >
          <Pie
            paddingAngle={1}
            dataKey="value"
           // isAnimationActive={true}
            data={data}
            
            outerRadius={60}
            label
            labelLine
          >
            {cells}
          
          </Pie>
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            onMouseEnter={(data, index, event) => setActiveIndex(index)}
            onMouseLeave={(data, index, event) => setActiveIndex(-1)}
          />
          <Tooltip/>
         
        </PieChart>
      </ResponsiveContainer>

  )

}


export default HarvestResultPieChart;
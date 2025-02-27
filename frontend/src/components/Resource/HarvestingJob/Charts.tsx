import { useTheme } from "@mui/material";
import { useMemo, useState } from "react";
import { useTheme as useRaTheme, useRecordContext } from "react-admin";
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
    "unhandled": currentTheme === 'dark' ? theme.palette.error.dark: theme.palette.error.light
  }), [currentTheme])

  const data = useMemo(() => {
    const total = record?.totalRecords

    const newDatasetRecords = record?.newDatasetRecords?.length || 0
    const existingDatasetRecords = record?.existingDatasetRecords?.length || 0
    const updatedDatasetRecords = record?.updatedDatasetRecords?.length || 0
    
    const handledDatasetRecords = newDatasetRecords + existingDatasetRecords + updatedDatasetRecords

    const newServiceRecords = record?.newServiceRecords?.length || 0
    const existingServiceRecords = record?.existingServiceRecords?.length || 0
    const updatedServiceRecords = record?.updatedServiceRecords?.length || 0

    const handledServiceRecords = newServiceRecords + existingServiceRecords + updatedServiceRecords
    const unhandledRecords = total - handledDatasetRecords - handledServiceRecords

    return [
      ...unhandledRecords >0 ? [{ id:'u_r', name: 'Unhandled Records', value: unhandledRecords, color: "unhandled" }]: [],
      ...newDatasetRecords > 0 ? [{ id:'n_d', name: 'New Datasets', value: newDatasetRecords, color: "new" }]: [],
      ...existingDatasetRecords > 0 ? [{ id:'e_d', name: 'Existing Datasets', value: existingDatasetRecords, color: "existing" }]: [],
      ...updatedDatasetRecords > 0 ? [{ id:'u_d', name: 'Updated Datasets', value: updatedDatasetRecords, color: "updated" }]: [],
      ...newServiceRecords > 0 ? [{ id:'n_s', name: 'New Services', value: newServiceRecords, color: "new" }]: [],
      ...existingServiceRecords > 0 ? [{ id:'e_s', name: 'Existing Services', value: existingServiceRecords, color: "existing" }]: [],
      ...updatedServiceRecords > 0 ? [{ id:'u_s', name: 'Updated Services', value: updatedServiceRecords, color: "updated" }]: [],
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
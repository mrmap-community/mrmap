import { BarPlot, ChartContainer, ChartsLegend, ChartsTooltip, ChartsXAxis } from '@mui/x-charts';
import { mangoFusionPalette } from '@mui/x-charts/colorPalettes';
import { subDays } from 'date-fns';
import { useMemo, type ReactNode } from 'react';
import { useGetList, useListContext } from 'react-admin';
import ResourceListCard from './Cards/ResourceListCard';
const styles = {
  flex: { display: 'flex' },
  flexColumn: { display: 'flex', flexDirection: 'column' },
  leftCol: { flex: 1, marginRight: '0.5em' },
  rightCol: { flex: 1, marginLeft: '0.5em' },
  singleCol: { marginTop: '1em', marginBottom: '1em' },
};

interface TotalByDay {
  date: number;
  total: number;
}

const lastDay = new Date();
const lastMonthDays = Array.from({ length: 30 }, (_, i) => subDays(lastDay, i));
const aMonthAgo = subDays(new Date(), 30);

const dateFormatter = (date: number): string =>
    new Date(date).toLocaleDateString();


const Spacer = () => <span style={{ width: '1em' }} />;

const DatasetMetadataChart = () => {
  const { total } = useListContext();
  const { data } = useGetList('StatisticalDatasetMetadataRecord', {sort: {field: "id", order: "DESC"}})

  const organizedData = useMemo(()=>{
      return data?.map((record, index) => {
        if (index === 0) {
          record["total"] = total
          return record
        }
        record["total"] = data[index-1]["total"] - data[index-1]["new"] + data[index-1]["deleted"]
        return record
      }).reverse()
  },[total, data])

  const series = useMemo(() => {
    const newDataSeries = []
    const deletedDataSeries = []
    const updatedDataSeries = []
    const series = [
      { type: 'bar', data: newDataSeries, label:'new' ,},
      { type: 'bar', data: deletedDataSeries, label:'deleted'},
      { type: 'bar', data: updatedDataSeries, label:'updated'},
    ]
  
    organizedData?.forEach(data => {
      newDataSeries.push(data.new ?? 0)
      deletedDataSeries.push(data.deleted ?? 0)
      updatedDataSeries.push(data.updated ?? 0)
    })

    return series
  }, [organizedData])

  const xAxis = useMemo(()=>(
    [{
      scaleType: 'band',
      data: organizedData?.map(data => (data.id)) || [],
      id: 'x-axis-id'
    }]
  ),[organizedData])

  return (
    <ChartContainer
        series={series}
        xAxis={xAxis}
        yAxis={[{ label: 'rainfall (mm)', width: 60 }]}
        colors={mangoFusionPalette}
        height={300}
      >
          <BarPlot/>

          <ChartsLegend direction="horizontal" />
          <ChartsXAxis  axisId="x-axis-id" />
          <ChartsTooltip />
        </ChartContainer >
  )


}

const Dashboard = (): ReactNode => {
  return (
    <div style={styles.singleCol}>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'WebMapService'} withList={false}/>
          <Spacer />
          <ResourceListCard resource={'Layer'} withList={false}/>
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'WebFeatureService'} withList={false}/>
          <Spacer />
          <ResourceListCard resource={'FeatureType'} withList={false}/> {/* <OrderChart orders={recentOrders} /> */}
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'CatalogueService'} withList={false} />
          <Spacer />
          <ResourceListCard resource={'DatasetMetadataRecord'} withList={false} >
            <DatasetMetadataChart/>  
          </ResourceListCard>
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'Organization'} />
          <Spacer />
          <ResourceListCard resource={'User'} />
        </div>
      </div>
    </div>
  )
}

export default Dashboard

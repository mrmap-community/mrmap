import { subDays } from 'date-fns';
import { useMemo, type ReactNode } from 'react';
import { useGetList, useListContext } from 'react-admin';
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
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

  const chartData = useMemo(()=>{
      return data?.map((record, index) => {
        if (index === 0) {
          record["total"] = total
          return record
        }
        record["total"] = data[index-1]["total"] - data[index-1]["new"] + data[index-1]["deleted"]
        return record
      }).reverse()
  },[total, data])

  return (
    <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
            <ComposedChart data={chartData}>
                <defs>
                    <linearGradient
                        id="colorUv"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                    >
                        <stop
                            offset="5%"
                            stopColor="#8884d8"
                            stopOpacity={0.8}
                        />
                        <stop
                            offset="95%"
                            stopColor="#8884d8"
                            stopOpacity={0}
                        />
                    </linearGradient>
                </defs>
                <XAxis
                    dataKey="day"
                    //name="Day"
                    //type="da"
                    //scale="time"
                    //domain={[
                    //    addDays(aMonthAgo, 1).getTime(),
                    //    new Date().getTime(),
                    //]}
                    tickFormatter={dateFormatter}
                />
                <YAxis 
                  dataKey="total" 
                  //name="Records" 
                  // unit="pieces" 
                />
                <CartesianGrid strokeDasharray="3 3" />
                <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    //formatter={(value: any) =>
                    //    new Intl.NumberFormat(undefined, {
                    //        style: 'currency',
                    //        currency: 'USD',
                    //    }).format(value)
                    //}
                    labelFormatter={(label: any) =>
                        dateFormatter(label)
                    }
                />
                <Legend />
                <Area
                    type="monotone"
                    dataKey="total"
                    stroke="#8884d8"
                    strokeWidth={2}
                    fill="url(#colorUv)"
                />
                <Bar dataKey="new" barSize={20} fill="#009900" />
                <Bar dataKey="deleted" barSize={20} fill="#cc0000" />
                <Bar dataKey="updated" barSize={20} fill="#0066cc" />
            </ComposedChart>
        </ResponsiveContainer>
    </div>

);
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

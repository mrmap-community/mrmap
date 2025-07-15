import {
  ChipField,
  ChipFieldProps,
  DataTable,
  DateField,
  List,
  ListProps,
  useFieldValue,
  useResourceDefinition,
} from 'react-admin';

import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useHttpClientContext } from '../../../../context/HttpClientContext';
import JsonApiReferenceField from '../../../../jsonapi/components/ReferenceField';


const HistoryTypField = ({...props}: ChipFieldProps) => {

  const value = useFieldValue(props);

  const color = useMemo(()=>{
    switch(value) {
      case 'created':
        return 'success'
      case 'deleted':
        return 'error'
      case 'updated':
        return 'primary'
      default:
        return 'default'
    }
  },[value])

  return (
    <ChipField
      color={color}
      {...props}
    />
  )

};

export interface HistoryListProps extends Partial<ListProps> {
  
}


const HistoryList = (
   {...rest}: HistoryListProps
) => {
  const { id } = useParams()
  
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api])
  
  if (!hasHistoricalEndpoint){
    return <></>
  }

  return (
    <List
      resource={`Historical${name}`}
      actions={<></>}
      perPage={5}
      key={`Historical${name}`}
      storeKey={`Historical${name}`}
      sx={{
          '& .RaList-main': {
            width: '90%',
            //width: `calc(${open ? '60vw' : '80vw'} - ${open ? '240px' : '50px - 2em'})`,
            //maxHeight: 'calc(50vh - 174px )', // 174px ==> 50 appbar, 52 pagination, 64 table actions, 8 top padding
            overfloxX: 'hidden',
            marginLeft: "1em",
            marginRight: "1em",
            marginBottom: "1em",
            overflowX: 'scroll',
          },
        }}
      filter={id ? {'history_relation': id}: undefined}
      {...rest}
    >
      <DataTable
        bulkActionButtons={false}
      >
        <DataTable.Col source="historyDate" label="resources.ChangeLog.historyDate">
          <DateField source="historyDate" showTime/>
        </DataTable.Col>
        <DataTable.Col source="historyUser" label="resources.ChangeLog.historyUser">
          <JsonApiReferenceField source='historyUser' reference='User'/>
        </DataTable.Col>
        <DataTable.Col source="historyRelation" label="resources.ChangeLog.historyRelation" disableSort>
          <JsonApiReferenceField source='historyRelation' reference={name}/>
        </DataTable.Col>
        <DataTable.Col source="historyType" label="resources.ChangeLog.historyType" disableSort field={HistoryTypField}/>
      </DataTable>
    </List>
  );
};

export default HistoryList;

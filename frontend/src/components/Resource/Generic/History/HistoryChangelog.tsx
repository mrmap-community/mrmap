import type { TimelineRecord } from './HistoryTimeline';

import { Fragment, useMemo } from 'react';
import {
  ChipField,
  ChipFieldProps,
  DataTable,
  DateField,
  DateInput,
  Filter,
  List,
  ListProps,
  SelectInput,
  useFieldValue,
  useRecordContext,
  useResourceDefinition,
  useTranslate,
} from 'react-admin';
import { useParams } from 'react-router-dom';

import { useHttpClientContext } from '../../../../context/HttpClientContext';
import JsonApiReferenceField from '../../../../jsonapi/components/ReferenceField';
import HistoryEventDetails from './HistoryEventDetails';


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

export type HistoryChangelogProps = Partial<ListProps>;

/** Event type and date range filters of the full changelog; the backend historical endpoints answer all of them. */
const HistoryFilters = () => {
  const translate = useTranslate();
  return (
    <Filter>
      <SelectInput
        source="history_type"
        label={translate('historyList.eventType', { _: 'Event' })}
        choices={[
          { id: '+', name: translate('historyList.created', { _: 'Created' }) },
          { id: '~', name: translate('historyList.updated', { _: 'Updated' }) },
          { id: '-', name: translate('historyList.deleted', { _: 'Deleted' }) },
        ]}
      />
      <DateInput source="history_date__gte" label={translate('historyList.dateFrom', { _: 'Changed from' })} />
      <DateInput source="history_date__lte" label={translate('historyList.dateTo', { _: 'Changed to' })} />
    </Filter>
  );
};

/** Expand panel of the changelog table, showing the previous and new value of every changed field. */
const HistoryEventExpand = () => {
  const record = useRecordContext();
  const { name } = useResourceDefinition();
  if (!record) return null;
  return <HistoryEventDetails event={record as TimelineRecord} related={name} />;
};


const HistoryChangelog = ({
  ...rest
  }: HistoryChangelogProps) => {
  const { id } = useParams()
  
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api, name])
  
  if (!hasHistoricalEndpoint){
    return <Fragment></Fragment>
  }

  return (
    <List
      resource={`Historical${name}`}
      actions={<Fragment></Fragment>}
      filters={<HistoryFilters />}
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
        expand={HistoryEventExpand}
        expandSingle
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

export default HistoryChangelog;

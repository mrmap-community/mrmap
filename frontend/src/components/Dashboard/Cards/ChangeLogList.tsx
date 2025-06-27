import {
  ChipField,
  ChipFieldProps,
  DataTable,
  DateField,
  List,
  useFieldValue,
  useResourceDefinition,
  useTranslate
} from 'react-admin';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Accordion, AccordionDetails, AccordionSummary, Divider } from '@mui/material';
import { useMemo } from 'react';
import { useHttpClientContext } from '../../../context/HttpClientContext';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
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


const ChangeLogList = (
   
) => {
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api])
  
  const translate = useTranslate();

  if (!hasHistoricalEndpoint){
    return <></>
  }

  return (
      <>
        <Divider />
        <Accordion slotProps={{ heading: { component: 'h2' } }}>
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            aria-controls="panel1-content"
            id="panel1-header"
          >
            {translate('resources.ChangeLog.lastChanges')}
          </AccordionSummary>
          <AccordionDetails>
            <List
                  resource={`Historical${name}`}
                  actions={<></>}
                  perPage={5}
                  key={`Dashboard-Historical${name}`}
                  storeKey={`Dashboard.Historical${name}`}
                  sx={
                  {
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
                    
                  }
                }
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
          </AccordionDetails>
        </Accordion>
      </>
  );
};

export default ChangeLogList;

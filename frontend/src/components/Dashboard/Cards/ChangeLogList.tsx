import {
  useResourceDefinition,
  useTranslate
} from 'react-admin';

import ChangeCircleIcon from '@mui/icons-material/ChangeCircle';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Accordion, AccordionDetails, AccordionSummary, Divider } from '@mui/material';
import { useMemo, useState } from 'react';
import { useHttpClientContext } from '../../../context/HttpClientContext';
import HistoryList from '../../Resource/Generic/History/HistoryList';


const ChangeLogList = (
   
) => {
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api])
  
  const translate = useTranslate();
  const [expanded, setExpanded] = useState(false);
  
  if (!hasHistoricalEndpoint){
    return <></>
  }
  console.log(expanded)
  return (
      <>
        <Divider />
        <Accordion 
          slotProps={{ heading: { component: 'h2' } }}
          defaultExpanded={false}
          expanded={expanded}
          onChange={(event, expanded) => setExpanded(expanded)}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            aria-controls="panel1-content"
            id="panel1-header"
          >
            <ChangeCircleIcon fontSize='small'/> {translate('resources.ChangeLog.lastChanges') } 
          </AccordionSummary>
          <AccordionDetails >
            {expanded ? <HistoryList disableSyncWithLocation/>: null}
          </AccordionDetails>
        </Accordion>
      </>
  );
};

export default ChangeLogList;

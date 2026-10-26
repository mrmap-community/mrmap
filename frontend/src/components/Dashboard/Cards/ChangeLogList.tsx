import { Fragment, useMemo, useState } from 'react';
import {
  useResourceDefinition,
  useTranslate
} from 'react-admin';

import ChangeCircleIcon from '@mui/icons-material/ChangeCircle';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Accordion, AccordionDetails, AccordionSummary, Divider } from '@mui/material';

import { useHttpClientContext } from '../../../context/HttpClientContext';
import { SelectedRecordContextProvider } from '../../../jsonapi/components/SelectedRecordContext';
import HistoryList from '../../Resource/Generic/History/HistoryList';


const ChangeLogList = (
   
) => {
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api, name])
  
  const translate = useTranslate();
  const [expanded, setExpanded] = useState(false);
  
  if (!hasHistoricalEndpoint){
    return <Fragment></Fragment>
  }
  return (
      <Fragment>
        <Divider />
        <Accordion 
          slotProps={{ heading: { component: 'h2' } }}
          defaultExpanded={false}
          expanded={expanded}
          onChange={(event, expanded) => setExpanded(expanded)}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            aria-controls={`${name}-history-content`}
            id={`${name}-history-header`}
          >
            <ChangeCircleIcon fontSize='small'/> {translate('resources.ChangeLog.lastChanges') } 
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            {expanded ? (
              <SelectedRecordContextProvider>
                <HistoryList variant="compact" related={name} />
              </SelectedRecordContextProvider>
            ) : null}
          </AccordionDetails>
        </Accordion>
      </Fragment>
  );
};

export default ChangeLogList;

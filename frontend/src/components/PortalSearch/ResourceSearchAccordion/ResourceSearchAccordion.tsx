import { FilterPayload, List, SimpleList, useResourceContext } from 'react-admin';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';

export interface ResourceSearchAccordionProps {
  name: string
  filter: FilterPayload
}


export const ResourceSearchAccordion = ({
  name,
  filter
}: ResourceSearchAccordionProps
) => {

  const resource = useResourceContext({resource: name});
  
  
  return (
      <Accordion>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="panel1-content"
          id="panel1-header"
        >
          {resource}
        </AccordionSummary>
        <AccordionDetails>
          <List resource={resource} filter={filter}>
            <SimpleList
              primaryText={record => record.title}
              secondaryText={record => record.abstract}
            />
          </List>
        </AccordionDetails>
      </Accordion>
  );
}
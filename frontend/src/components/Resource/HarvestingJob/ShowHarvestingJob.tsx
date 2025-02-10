import { BooleanField, NumberField, Show, TabbedShowLayout } from 'react-admin';
import JsonApiReferenceManyCount from '../../../jsonapi/components/JsonApiReferenceManyCountField';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';


const ShowHarvestingJob = () => { 
    return (
                
      <Show 
        queryOptions={{meta: {jsonApiParams:{include: 'service'}}}}
      >
        <TabbedShowLayout>

          <TabbedShowLayout.Tab label="summary">
            
            <JsonApiReferenceField source="service" reference="CatalogueService" label="Service" />
            <BooleanField source="harvestDatasets"/>
            <BooleanField source="harvestServices"/>
            <NumberField source="totalRecords"/>
            <JsonApiReferenceManyCount source="newDatasetRecords"/>

          </TabbedShowLayout.Tab>

          <TabbedShowLayout.Tab label="body" path="body">
            test
            <BooleanField source="harvestDatasets"/>

          </TabbedShowLayout.Tab>


        </TabbedShowLayout>

       
      </Show>
    )
};

export default ShowHarvestingJob
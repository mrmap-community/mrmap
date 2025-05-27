import { FormControl, FormHelperText, Input, InputLabel } from '@mui/material';
import XMLViewer from 'react-xml-viewer';

const xml = '<hello>World</hello>';

const CatalogueServiceClient = () => {
  
  
  
  return (
    <div>
      <FormControl>
        <InputLabel htmlFor="my-input">Email address</InputLabel>
        <Input id="my-input" aria-describedby="my-helper-text" />
        <FormHelperText id="my-helper-text">We'll never share your email.</FormHelperText>
      </FormControl>



      <XMLViewer 
        xml={xml} 
        collapsible={true}
        initialCollapsedDepth={3}
        showLineNumbers={true}
      />
    </div>
  );
}

export default CatalogueServiceClient;
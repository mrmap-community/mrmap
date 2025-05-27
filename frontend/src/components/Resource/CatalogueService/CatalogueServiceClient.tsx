import { FormControl, TextField } from '@mui/material';
import { useEffect, useState } from 'react';
import { useForm } from "react-hook-form";
import XMLViewer from 'react-xml-viewer';
const xml = '<hello>World</hello>';

const CatalogueServiceClient = () => {
  
  const {register, handleSubmit} = useForm();
  const [data, setData] = useState({});
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [cswUrl, setCswUrl] = useState('https://42.gdi-de.org/geonetwork/srv/ger/csw');

  useEffect(()=>{
    if (data !== undefined){
      const url = new URL(cswUrl)
      url.searchParams.set('VERSION', '2.0.2')
      url.searchParams.set('REQUEST', 'GetRecords')
      url.searchParams.set('SERVICE', 'CSW')
      url.searchParams.set('typeNames', 'gmd:MD_Metadata')
      url.searchParams.set('resultType', 'results')
      url.searchParams.set('outputSchema', 'http://www.isotc211.org/2005/gmd')
      url.searchParams.set('elementSetName', 'full')
      url.searchParams.set('constraintLanguage', 'FILTER')
      url.searchParams.set('CONSTRAINT_LANGUAGE_VERSION', '1.1.0')
      url.searchParams.set('Constraint','<ogc%3AFilter+xmlns%3Aogc%3D"http%3A%2F%2Fwww.opengis.net%2Fogc"><ogc%3AOr><ogc%3APropertyIsEqualTo><ogc%3APropertyName>type<%2Fogc%3APropertyName><ogc%3ALiteral>dataset<%2Fogc%3ALiteral><%2Fogc%3APropertyIsEqualTo><ogc%3APropertyIsEqualTo><ogc%3APropertyName>type<%2Fogc%3APropertyName><ogc%3ALiteral>service<%2Fogc%3ALiteral><%2Fogc%3APropertyIsEqualTo><%2Fogc%3AOr><%2Fogc%3AFilter>')
      url.searchParams.set('maxRecords', '100')
      url.searchParams.set('startPosition', '1')




      setLoading(true)
      fetch(url)
      .then(response => (
        response.text())).then(response => {
          setLoading(false);
          setResponse(response);
      })
      .catch(error => {
        setError(error);
        setLoading(false);
      })

    }
  },[data])

  return (
    <div>
      <form onSubmit={handleSubmit((data) => setData(data))}>
        <FormControl >
          <TextField
            size="small"
            variant='outlined'
            label='serach'
            {...register("search")}
          />
        
        </FormControl>
      </form>



      <XMLViewer 
        xml={response} 
        collapsible={true}
        initialCollapsedDepth={3}
        showLineNumbers={true}
      />
    </div>
  );
}

export default CatalogueServiceClient;

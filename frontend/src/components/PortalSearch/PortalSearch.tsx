import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { FilterList, FilterListItem, FilterLiveSearch, FilterPayload, SavedQueriesList } from 'react-admin';

import CategoryIcon from '@mui/icons-material/LocalOffer';
import MailIcon from '@mui/icons-material/MailOutline';
import { Card, CardContent, FormControl, FormHelperText, Grid, Input, InputLabel, TextField } from '@mui/material';

import { ResourceSearchAccordion } from './ResourceSearchAccordion/ResourceSearchAccordion';


export const FilterSidebar = () => (
  <Card sx={{ order: -1, mr: 2, mt: 9, width: 200 }}>
      <CardContent>
          <FilterLiveSearch source={'search'} />
          <SavedQueriesList />
          <FilterList label="Subscribed to newsletter" icon={<MailIcon />}>
              <FilterListItem label="Yes" value={{ has_newsletter: true }} />
              <FilterListItem label="No" value={{ has_newsletter: false }} />
          </FilterList>
          <FilterList label="Category" icon={<CategoryIcon />}>
              <FilterListItem label="Tests" value={{ category: 'tests' }} />
              <FilterListItem label="News" value={{ category: 'news' }} />
              <FilterListItem label="Deals" value={{ category: 'deals' }} />
              <FilterListItem label="Tutorials" value={{ category: 'tutorials' }} />
          </FilterList>
      </CardContent>
  </Card>
);

export const CustomFilter = () => (
  <FormControl>
    <InputLabel htmlFor="my-input">Search</InputLabel>
    <Input id="my-input" aria-describedby="my-helper-text" />
    <FormHelperText id="my-helper-text">We'll never share your email.</FormHelperText>
  </FormControl>

);


const PortalSearch = (): ReactNode => {
  const [search, setSearch] = useState("")

  const handleSubmit = useCallback((event) => {
    console.log(event)
    event.preventDefault();
    alert("Form Submitted");
  }, []);

  const filter = useMemo<FilterPayload>(()=>{
    return {"search": search}
  },[search]);
  
  return (
    
    <Grid container>
      <Grid item>
        <form onSubmit={handleSubmit}>
          <FormControl>
          <TextField 
              label="Search"
              onChange={e => setSearch(e.target.value)}        
            />
          
        </FormControl>
        </form>
      </Grid>

      <Grid item>
        <ResourceSearchAccordion name="WebMapService" filter={filter}/>
        <ResourceSearchAccordion name="DatasetMetadata" filter={filter}/>
      </Grid>
    </Grid>
  )
}

export default PortalSearch

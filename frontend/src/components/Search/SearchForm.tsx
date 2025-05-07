import { FormControl, TextField } from '@mui/material';
import { useCallback } from 'react';

const SearchInput = () => {
  const onSubmit = useCallback((data) => {
    console.log(data)
  },[]);


  return (
    <FormControl onSubmit={onSubmit} >
      <TextField
        size="small"
        variant='outlined'
        label='serach'
        onSubmit={onSubmit}
        onKeyDown={onSubmit}
      />
    </FormControl>
  )
};


export default SearchInput
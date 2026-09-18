import { Box } from '@mui/material';
import {
  ListNoResults,
  useResourceDefinition,
  useTranslate
} from 'react-admin';



const EmptyListWithFilter = () => {
  const { name } = useResourceDefinition();
  const translate = useTranslate();
  
  
  return (
    <Box
      sx={{
        minHeight: 450,

        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',

        textAlign: 'center',
        p: 3,
      }}
    >
      <Box
        component="img"
        src="mr_map_empty_list_with_filter.png"
        alt={translate("ra.page.empty",  {name})}
        sx={{
          width: 'clamp(220px, 30vw, 420px)',
          maxWidth: '90%',
          height: 'auto',
          objectFit: 'contain',
          mb: 2,
        }}
      />

      <ListNoResults/>
    </Box>
  );
};

export default EmptyListWithFilter;
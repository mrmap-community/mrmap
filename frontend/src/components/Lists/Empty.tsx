import { Box, Typography } from "@mui/material";
import { useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import CreateDialogButton from "../Dialog/CreateDialogButton";


export interface EmptyListProps {
  resource?: string;
  defaultValue?: string | number | readonly string[] | undefined;
}

const EmptyList = ({...rest}: EmptyListProps) => {
  const resource = useResourceContext({resource: rest?.resource})
  const { name } = useResourceDefinition({resource: resource})
  const translate = useTranslate();

  return (
    <Box sx={{
      textAlign:"center",
      m:1
    }}>
      <Typography 
        sx={{
          variant:"h4",
          
        }}
        
      >
          {translate('ra.page.empty', {name: name})}
      </Typography>
      <Typography variant="body1">
          {translate('ra.page.invite')}
      </Typography>
      <CreateDialogButton 
        createDialogProps={{
          resource: resource,
          defaultValue: rest.defaultValue 
        }}
        buttonProps={{variant: 'contained'}}
      />
    </Box>
  )
}


export default EmptyList;
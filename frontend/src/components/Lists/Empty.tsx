import { Box, Typography } from "@mui/material";
import { useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import { CreateDialogProps } from "../Dialog/CreateDialog";
import CreateDialogButton from "../Dialog/CreateDialogButton";


export interface EmptyListProps {
  createDialogProps?: CreateDialogProps  
}

const EmptyList = ({createDialogProps}: EmptyListProps) => {
  const resource = useResourceContext({resource: createDialogProps?.resource})
  const { name, hasCreate } = useResourceDefinition({resource: resource})
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
      
      {hasCreate && <CreateDialogButton
        createDialogProps={createDialogProps}
        buttonProps={{variant: 'contained'}}
      />}
    </Box>
  )
}


export default EmptyList;
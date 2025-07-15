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
    <Box textAlign="center" m={1}>
      <Typography variant="h4" paragraph>
          {translate('ra.page.empty', {name: name})}
      </Typography>
      <Typography variant="body1">
          {translate('ra.page.invite')}
      </Typography>
      <CreateDialogButton 
        resource={resource} 
        buttonProps={{variant: 'contained'}}
        defaultValue={rest.defaultValue} 
      />
    </Box>
  )
}


export default EmptyList;
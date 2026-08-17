import { Box, IconButton, Stack, Tooltip } from '@mui/material';
import { useSystemTime } from "../../jsonapi/hooks/useSystemTime";


import CircleIcon from '@mui/icons-material/Circle';

import GitHubIcon from '@mui/icons-material/GitHub';
import { useMemo } from 'react';
import { ReadyState } from 'react-use-websocket';
import { useHttpClientContext } from '../../context/HttpClientContext';

const Footer = () => {
  const systemTime = useSystemTime();
  const { api, realtimeIsReady } = useHttpClientContext()
  const readyStateColor = useMemo(()=>{
    switch(realtimeIsReady){
      case ReadyState.CONNECTING:
        return 'warning'
      case ReadyState.OPEN:
        return 'success'
      case ReadyState.CLOSING:
      case ReadyState.CLOSED:
        return 'error'
      case ReadyState.UNINSTANTIATED:
      default:
        return 'info'

    }
  },[realtimeIsReady])
  return (
    <Stack
      direction="row"
      sx={{justifyContent:"space-between", alignItems:"center"}}
    >
      <Box 
        sx={{paddingLeft: 2}}
      >
          v.{api?.document.info.version}
      </Box>
      <Box  >
        <IconButton 
          href="https://github.com/mrmap-community" 
          target="_blank"
        >
          <GitHubIcon />
        </IconButton>
      </Box>
      <Stack
        direction="row"
        sx={{
          justifyContent:'space-between',
          alignItems:"center"
        }}
        //sx={{alignItems: "center",justifyContent:"space-between"}}
      >
        <Box>
          {systemTime ?? ''}
        </Box>
        <Box>
          <Tooltip title={
            realtimeIsReady === ReadyState.OPEN 
            ? 'Backend is connected'
            : 'Connection to backend lost'
            }
          >
            <IconButton>
              <CircleIcon color={readyStateColor}/>
            </IconButton>
          </Tooltip>
        </Box>
      </Stack>
    </Stack>
  )
}

export default Footer
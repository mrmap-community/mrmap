import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton } from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { useCallback, useState } from 'react';
import { DeleteButton, Edit, Form, RaRecord, RecordRepresentation, SaveButton, useNotify, useTranslate } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import AllowedWebMapServiceOperationFields from '../AllowedWebMapServiceOperation/AllowedWebMapServiceOperationFields';

const WebMapServiceOperationUrlsListWithEdit = () => {
  
  const translate = useTranslate();
  const notify = useNotify();

  const [clickedRow, setClickedRow] = useState<RaRecord>()

  const onEditSuccess = useCallback(()=>{
    setClickedRow(undefined)
    notify(`resources.AllowedWebMapServiceOperation.notifications.updated`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate('ra.notification.updated', {
              smart_count: 1,
          })
      },
      undoable: false,
  });
  },[])

  const onDeleteSuccess = useCallback(()=>{
    setClickedRow(undefined)
    notify(`resources.AllowedWebMapServiceOperation.notifications.deleted`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate('ra.notification.deleted', {
              smart_count: 1,
          })
      },
      undoable: false,
  });
  },[])

  return (
    <>
      <ListGuesser 
        resource='WebMapServiceOperationUrl'
        rowActions={<></>}
        onRowClick={(record) => setClickedRow(record)}
      />
      {
      // only render Edit if clickedRow is defined. Otherwise the Edit compononent will get the id from the url path, which causes in wron id of wrong resources.
      clickedRow ?
      /* Edit and Form component needed to be outside the Dialog component. 
        Otherwise the scroll feature is broken.
        See: https://github.com/mui/material-ui/issues/13253 
      */
      <Edit
        mutationMode='pessimistic'
        resource="WebMapServiceOperationUrl"
        id={clickedRow?.id}
        record={clickedRow}
        redirect={false}
        mutationOptions={{onSuccess: onEditSuccess}}
        sx={{
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Form>
          <Dialog 
            open={!!clickedRow}
            onClose={() => setClickedRow(undefined)}
            scroll={'paper'}
            aria-labelledby="scroll-dialog-title"
            aria-describedby="scroll-dialog-description"
          >
            <DialogTitle id="scroll-dialog-title">
              <Box display="flex" alignItems="center">
                <Box flexGrow={1} >
                  <RecordRepresentation record={clickedRow}/>
                </Box>
                <Box>
                  <IconButton onClick={() => setClickedRow(undefined)}>
                    <CloseIcon />
                  </IconButton>
                </Box>
              </Box>
              
            </DialogTitle>

            <DialogContent 
              dividers={true} 
              id="scroll-dialog-description"
            >
              <AllowedWebMapServiceOperationFields />  
            </DialogContent>

            <DialogActions style={{ justifyContent: "space-between" }}>
                  <SaveButton mutationOptions={{onSuccess: onEditSuccess}} type='button'/>
                  <DeleteButton redirect={false} mutationOptions={{onSuccess: onDeleteSuccess}}/>
            </DialogActions>
          
          </Dialog>
        </Form>
      </Edit>
    : null} 
    </>
  )
}


export const WebMapServiceOperationUrlsTab = () => {
  return (
    <WebMapServiceOperationUrlsListWithEdit />          
  )
}



export default WebMapServiceOperationUrlsTab
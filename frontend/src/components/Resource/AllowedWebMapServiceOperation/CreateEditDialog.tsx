import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton } from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { useCallback, useMemo } from 'react';
import { Create, DeleteButton, Edit, Form, RaRecord, RecordRepresentation, SaveButton, useNotify, useTranslate } from 'react-admin';
import AllowedWebMapServiceOperationFields from './AllowedWebMapServiceOperationFields';

export interface CreateEditDialogProps {
  open: boolean;
  record?: RaRecord;
  onClose: () => void;
  onEditSuccess?: () => void;
  onCreateSuccess?: () => void;
  onDeleteSuccess?: () => void;
  additionalActions?: React.ReactNode;
}

const CreateEditDialog = ({
  open,
  record,
  onClose,
  onEditSuccess,
  onCreateSuccess,
  onDeleteSuccess,
  additionalActions
}: CreateEditDialogProps) => {
  const translate = useTranslate();
  const notify = useNotify();

  const isEditMode = useMemo(() => !!record, [record]);

  const handleEditSuccess = useCallback(() => {
    onClose();
    onEditSuccess?.();
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
  }, [onClose, onEditSuccess, notify, translate]);

  const handleCreateSuccess = useCallback(() => {
    onClose();
    onCreateSuccess?.();
    notify(`resources.AllowedWebMapServiceOperation.notifications.created`, {
      type: 'info',
      messageArgs: {
        smart_count: 1,
        _: translate('ra.notification.created', {
          smart_count: 1,
        })
      },
      undoable: false,
    });
  }, [onClose, onCreateSuccess, notify, translate]);

  const handleDeleteSuccess = useCallback(() => {
    onClose();
    onDeleteSuccess?.();
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
  }, [onClose, onDeleteSuccess, notify, translate]);

  const dialogTitle = useMemo(() => {
    if (isEditMode) {
      return <RecordRepresentation record={record} />;
    }
    return `Create AllowedWebMapServiceOperation`;
  }, [isEditMode, record]);

  if (!open) {
    return null;
  }

  return (
    <>
      {isEditMode ? (
        <Edit
          mutationMode="pessimistic"
          resource="AllowedWebMapServiceOperation"
          id={record?.id}
          record={record}
          redirect={false}
          mutationOptions={{ onSuccess: handleEditSuccess }}
          sx={{
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <Form>
            <Dialog
              open={open}
              onClose={onClose}
              scroll="paper"
              aria-labelledby="scroll-dialog-title"
              aria-describedby="scroll-dialog-description"
              maxWidth="sm"
              fullWidth
            >
              <DialogTitle id="scroll-dialog-title">
                <Box display="flex" alignItems="center">
                  <Box flexGrow={1}>{dialogTitle}</Box>
                  <Box>
                    <IconButton onClick={onClose}>
                      <CloseIcon />
                    </IconButton>
                  </Box>
                </Box>
              </DialogTitle>

              <DialogContent dividers={true} id="scroll-dialog-description">
                <AllowedWebMapServiceOperationFields />
              </DialogContent>

              <DialogActions style={{ justifyContent: 'space-between' }}>
                <SaveButton mutationOptions={{ onSuccess: handleEditSuccess }} type="button" />
                <Box display="flex" gap={1}>
                  <DeleteButton redirect={false} mutationOptions={{ onSuccess: handleDeleteSuccess }} />
                  {additionalActions}
                </Box>
              </DialogActions>
            </Dialog>
          </Form>
        </Edit>
      ) : (
        <Create
          resource="AllowedWebMapServiceOperation"
          redirect={false}
          mutationOptions={{ onSuccess: handleCreateSuccess }}
          sx={{
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <Form>
            <Dialog
              open={open}
              onClose={onClose}
              scroll="paper"
              aria-labelledby="scroll-dialog-title"
              aria-describedby="scroll-dialog-description"
              maxWidth="sm"
              fullWidth
            >
              <DialogTitle id="scroll-dialog-title">
                <Box display="flex" alignItems="center">
                  <Box flexGrow={1}>{dialogTitle}</Box>
                  <Box>
                    <IconButton onClick={onClose}>
                      <CloseIcon />
                    </IconButton>
                  </Box>
                </Box>
              </DialogTitle>

              <DialogContent dividers={true} id="scroll-dialog-description">
                <AllowedWebMapServiceOperationFields />
              </DialogContent>

              <DialogActions style={{ justifyContent: 'space-between' }}>
                <SaveButton mutationOptions={{ onSuccess: handleCreateSuccess }} type="button" />
                {additionalActions}
              </DialogActions>
            </Dialog>
          </Form>
        </Create>
      )}
    </>
  );
};

export default CreateEditDialog;

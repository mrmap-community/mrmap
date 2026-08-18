import { Box, Typography } from '@mui/material';
import {
  useResourceContext,
  useResourceDefinition,
  useTranslate,
} from 'react-admin';

import { CreateDialogProps } from '../Dialog/CreateDialog';
import CreateDialogButton from '../Dialog/CreateDialogButton';

export interface EmptyListProps {
  createDialogProps?: CreateDialogProps;
}

const EmptyList = ({ createDialogProps }: EmptyListProps) => {
  const resource = useResourceContext({
    resource: createDialogProps?.resource,
  });

  const { name, hasCreate } = useResourceDefinition({
    resource,
  });

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
        src="mr_map_empty_list.png"
        alt="Empty list"
        sx={{
          width: 'clamp(220px, 30vw, 420px)',
          maxWidth: '90%',
          height: 'auto',
          objectFit: 'contain',
          mb: 2,
        }}
      />

      <Typography
        variant="h4"
        sx={{
          mb: 1,
        }}
      >
        {translate('ra.page.empty', { name })}
      </Typography>

      <Typography
        variant="body1"
        color="text.secondary"
        sx={{
          mb: 3,
        }}
      >
        {translate('ra.page.invite')}
      </Typography>

      {hasCreate && (
        <CreateDialogButton
          createDialogProps={createDialogProps}
          buttonProps={{
            variant: 'contained',
          }}
        />
      )}
    </Box>
  );
};

export default EmptyList;
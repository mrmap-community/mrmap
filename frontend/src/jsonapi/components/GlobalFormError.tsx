import { ValidationError } from 'react-admin';
import { useFormState } from 'react-hook-form';

import { Alert } from '@mui/material';

const GlobalFormError = () => {
  const { errors } = useFormState();
  const message = errors.root?.serverError?.message;

  if (typeof message !== 'string') return null;

  return (
    <Alert severity="error" sx={{ width: '100%', whiteSpace: 'pre-line' }}>
      <ValidationError error={message} />
    </Alert>
  );
};

export default GlobalFormError;

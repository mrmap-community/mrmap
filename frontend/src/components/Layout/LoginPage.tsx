import { useState, type ComponentProps } from 'react';
import { Login as RaLogin, LoginForm, useTranslate } from 'react-admin';

import Typography from '@mui/material/Typography';

import { consumeSessionEndReason } from '../../providers/authProvider';

/**
 * The login page of #834: react-admin's own form plus, when the session ended
 * on its own, the reason on top of it. The credential was cleared before the
 * redirect, so without this the user would stare at an empty form having lost
 * a day's work to a silent expiry; `consumeSessionEndReason` answers the key
 * once, so a later deliberate visit to /login shows no stale message.
 *
 * `Login` replaces its default form with its children, so the form itself is
 * react-admin's exported `LoginForm` - the very component the plain `Login`
 * renders - kept, with the optional reason above it. The alternatives
 * considered were react-admin's own `Login` page unchanged - it renders no
 * state the provider set - and a `useNotify` toast, which react-admin's
 * logout path suppresses for a caller whose `checkAuth` already fails,
 * exactly the expired case.
 */
const LoginPage = (props: ComponentProps<typeof RaLogin>) => {
  // consumed once per mount; re-renders keep the same answer
  const [reason] = useState(consumeSessionEndReason);
  const translate = useTranslate();

  return (
    <RaLogin {...props}>
      {reason !== undefined && (
        <Typography color="error" align="center" role="status">
          {translate(reason)}
        </Typography>
      )}
      <LoginForm />
    </RaLogin>
  );
};

export default LoginPage;

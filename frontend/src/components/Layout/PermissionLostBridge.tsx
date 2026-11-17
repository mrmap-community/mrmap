import { useEffect, type ReactNode } from 'react';
import { useRefresh } from 'react-admin';

import { useQueryClient } from '@tanstack/react-query';

import { onPermissionLost } from '../../providers/authProvider';

/**
 * The renderless revalidation observer of #834: mounted like the other
 * layout bridges, it listens for the authProvider's `permission_denied`
 * answer - the server refused the caller while their session stayed valid,
 * e.g. an administrator revoked their role in another session - and then asks
 * the same pair the Members screen applies after a self-revocation (#727):
 * drop react-admin's cached `canAccess` answers so menus and buttons re-run
 * against the freshened snapshot, and refresh the open screens so their lists
 * answer from the backend again. Without it the loss would only surface on
 * the next navigation.
 */
const PermissionLostBridge = (_props: Record<string, never>): ReactNode => {
  const refresh = useRefresh();
  const queryClient = useQueryClient();

  useEffect(
    () =>
      onPermissionLost(() => {
        queryClient.invalidateQueries({ queryKey: ['canAccess'] });
        refresh();
      }),
    [refresh, queryClient],
  );

  return null;
};

export default PermissionLostBridge;

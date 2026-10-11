import { useCallback } from 'react';
import { type RaRecord, type RedirectionSideEffect, useNotify, useRedirect, useTranslate } from 'react-admin';
import { useReferenceManyErrors } from '../components/ReferenceManyErrorsProvider';

export default function useGuesserSuccess({ resource, action, redirectTo, undoable }: {
  resource: string;
  action: 'created' | 'update';
  redirectTo?: RedirectionSideEffect;
  undoable: boolean;
}) {
  const notify = useNotify();
  const redirect = useRedirect();
  const translate = useTranslate();
  const { getErrors } = useReferenceManyErrors();

  return useCallback((data: RaRecord) => {
    const referenceManyErrors = getErrors();
    const hasErrors = referenceManyErrors.length > 0;
    const message = hasErrors ? 'updated_with_errors' : action;
    notify(`resources.${resource}.notifications.${message}`, {
      type: hasErrors ? 'warning' : 'info',
      messageArgs: { smart_count: 1, _: translate(`ra.notification.${message}`, { smart_count: 1 }) },
      undoable,
    });
    if (hasErrors) {
      redirect('edit', resource, data.id, undefined, { referenceManyErrors });
    } else {
      redirect(redirectTo ?? 'list', resource, data.id, data);
    }
  }, [resource, action, redirectTo, undoable, getErrors, notify, redirect, translate]);
}

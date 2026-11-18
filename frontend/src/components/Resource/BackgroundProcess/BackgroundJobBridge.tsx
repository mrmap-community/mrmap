import { type ReactNode, useEffect, useRef } from 'react';
import { useNotify, useTranslate } from 'react-admin';

import { useBackgroundJobCenter } from './JobCenter/BackgroundJobCenterContext';

/** the quiet distance after which the failures arrived in a burst are told -
 *  long enough that the answers of one bulk run collapse into one message,
 *  short enough to stay in front of the user (the window the store's
 *  notification flush had before #1461 converged them) */
const NOTIFY_AGGREGATION_MILLISECONDS = 1000;

/**
 * the notification bridge (#1205): it replaces the per-event snackbar flood
 * the former `SnackbarObserver` caused.
 *
 * It is the thin subscriber #1461 converged the two job-state stacks into:
 * it owns no store, fetches nothing and subscribes no realtime topic - the
 * Background Job Center owns the state, the hydration and every websocket
 * subscription. The bridge only registers on the center's failure seam and
 * raises a React-Admin notification when a process becomes actionable,
 * aggregated, so a burst of failures is a single notification. Completions
 * are never told: they are what the drawer shows, not what the user must act
 * on; a failure recovered from the api (a reload or a reconnect replay) is
 * history and the center does not report it here either.
 *
 * It renders nothing.
 */
const BackgroundJobBridge = (): ReactNode => {
  const notify = useNotify();
  const translate = useTranslate();
  const { subscribeFailed } = useBackgroundJobCenter();

  // the failures which wait for their aggregation window, and the window
  const pending = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // the bridge of the aggregated failures to a React-Admin notification, once
  // per burst. The translate calls carry the literal keys - a key computed
  // into a variable cannot be traced back to the i18n files - and the
  // finished text goes to notify.
  useEffect(() => {
    return subscribeFailed((records) => {
      pending.current += records.length;
      if (timer.current !== undefined) return;
      timer.current = setTimeout(() => {
        timer.current = undefined;
        const count = pending.current;
        pending.current = 0;
        const message =
          count === 1
            ? translate('backgroundJobs.notification.failedOne', { count })
            : translate('backgroundJobs.notification.failedMany', { count });
        notify(message, { type: 'error' });
      }, NOTIFY_AGGREGATION_MILLISECONDS);
    });
  }, [subscribeFailed, notify, translate]);

  // a burst which had not reached its quiet moment dies with the bridge
  useEffect(
    () => () => {
      if (timer.current !== undefined) {
        clearTimeout(timer.current);
        timer.current = undefined;
      }
    },
    [],
  );

  return null;
};

export default BackgroundJobBridge;

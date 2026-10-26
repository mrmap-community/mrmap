import type { HistoryChangelogProps as ChangelogProps } from './HistoryChangelog';
import type { HistoryCompactFeedProps } from './HistoryCompactFeed';
import type { HistorySourcesCardProps } from './HistorySourcesCard';

import HistoryChangelog from './HistoryChangelog';
import HistoryCompactFeed from './HistoryCompactFeed';
import HistorySourcesCard from './HistorySourcesCard';

/**
 * The presentations one caller can ask of the history of a resource:
 *
 * - `table` (default): the paginated and filterable changelog of a resource,
 *   which its `history` route answers.
 * - `compact`: the latest events of a resource in dashboard cards or the aside
 *   of a list, optionally scoped to its selected record, with full values in a dialog.
 * - `timeline`: the newest-first merge of one or more event sources, which a
 *   service or record show composes from `historySources`.
 */
export type HistoryListProps =
  | ({ variant?: 'table' } & ChangelogProps)
  | ({ variant: 'compact' } & HistoryCompactFeedProps)
  | ({ variant: 'timeline' } & HistorySourcesCardProps);

/**
 * The single public history list of the frontend.
 *
 * Every screen which answers what changed asks this component and names its
 * variant; the presentations themselves are private to this folder. Callers
 * keep composing their sources (see `historySources`) and their scoping here,
 * and the component answers loading, empty and error states for every variant.
 */
const HistoryList = (props: HistoryListProps) => {
  if (props.variant === 'compact') {
    const { variant: _variant, ...rest } = props;
    return <HistoryCompactFeed {...rest} />;
  }
  if (props.variant === 'timeline') {
    const { variant: _variant, ...rest } = props;
    return <HistorySourcesCard {...rest} />;
  }
  const { variant: _variant, ...rest } = props;
  return <HistoryChangelog {...rest} />;
};

export default HistoryList;

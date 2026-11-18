import { Button, Link, useTranslate } from "react-admin";

import HistoryIcon from "@mui/icons-material/History";

/**
 * The link to the changelog route of a resource.
 *
 * `MrMapFrontend` registers a `history` child route for every resource whose
 * schema answers `list_Historical<Resource>`; that route answers the paginated
 * and filterable changelog (`HistoryList`'s `table` variant) and needs no id,
 * because a changelog of one record is reached from that record's own screen.
 * A route which nothing links to is not an audit trail an administrator finds,
 * which is why the administration screens name it in their toolbar (#741).
 *
 * The link is deliberately not gated by `canAccess` over the historical
 * resource: reading the changelog of the role tables is open to the same
 * accounts which read the tables themselves, and the server decides the
 * answer - a screen which hid the link would decide by guessing.
 */
export type HistoryChangelogLinkProps = {
  /** the resource whose changelog route to open, e.g. `RoleDefinition` */
  resource: string;
  /** label of the link, translated; a screen names its own wording (#741) */
  label: string;
};

const HistoryChangelogLink = ({
  resource,
  label,
}: HistoryChangelogLinkProps) => {
  const translate = useTranslate();

  return (
    <Button
      component={Link}
      to={`/${resource}/history`}
      size="small"
      startIcon={<HistoryIcon />}
    >
      {translate(label, { _: "Audit trail" })}
    </Button>
  );
};

export default HistoryChangelogLink;

import { useEffect, useState } from "react";
import {
  Labeled,
  useGetList,
  useRecordContext,
  useTranslate,
  type RaRecord,
} from "react-admin";

import { Typography } from "@mui/material";

import { getPermissionSnapshot } from "../../../../providers/authProvider";
import defaultRecordRepresentation from "../../defaultRecordRepresentation";

/** The name and nothing else, ordered as the organization screens order it;
 *  the read of the #737 scope asks the same page of the same resource. */
const ORGANIZATIONS_PAGE_SIZE = 100;

/** The organization of a service, as the api answers it: a resource
 *  identifier without a name, because a show request answers the relation of
 *  #733 but not the organization behind it. */
interface OwnerLinkage {
  id?: string | number;
}

const ownerIdOf = (record: RaRecord | undefined): string | undefined => {
  const owner = record?.owner as OwnerLinkage | undefined;
  const id = owner?.id;
  return id === undefined || id === null || id === "" ? undefined : String(id);
};

/**
 * The organization which owns a service, as the read-only `owner` relation of
 * #733 answers it.
 *
 * The name is not part of the service record, so it is asked for itself - but
 * through the organizations *list* rather than the record of the owner: that
 * list answers 200 to every signed-in caller
 * (`tests/django/accounts/test_groups_api_permissions.py`), while the record
 * of an organization hands out to nobody but its own members. The difference
 * is not cosmetic: a refused read reaches `authProvider.checkError`, which
 * ends an anonymous visit with a redirect to the login page and answers a
 * signed-in refusal with a permission-lost notification and a revalidation of
 * every open screen. A label must not do that to the page it sits on, and the
 * caller's memberships are not part of the permission snapshot of #836, so the
 * row cannot know in advance whether it may ask for one foreign organization.
 *
 * A caller without a session asks nothing at all: the organizations endpoint
 * refuses it, and the public read seam of #833 shows a service without naming
 * who owns it.
 *
 * `jsonapi/components/ReferenceField` was considered and does not fit: it
 * always links to `/<reference>/<id>/show`, and the `Organization` resource of
 * `components/Resource/Definition.tsx` registers no show screen, so the link
 * of that field leads nowhere. The name is therefore plain text; the way into
 * an organization is the members screen of #737.
 *
 * Like the #737 scope, the read knows the organizations of one page: an
 * instance beyond `ORGANIZATIONS_PAGE_SIZE` organizations answers the name of
 * the ones it shows, and the row of a further one says it cannot read it.
 */
const ServiceOwnerField = ({
  hintWhenAbsent = false,
}: {
  /** Whether a service which names no owner says so. Only a screen whose own
   *  request asks for the relation can tell an ownerless service - one of
   *  before ownership was stored - from a screen that did not ask about it, so
   *  only such a screen passes this. */
  hintWhenAbsent?: boolean;
}) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const ownerId = ownerIdOf(record);

  // Whether this caller has a session at all: without one no organization is
  // readable. Read in an effect, the way the #737 scope reads the snapshot,
  // because answering it touches the cached who-am-i access.
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    setSignedIn(getPermissionSnapshot() !== undefined);
  }, []);

  const { data, error, isPending } = useGetList(
    "Organization",
    {
      pagination: { page: 1, perPage: ORGANIZATIONS_PAGE_SIZE },
      sort: { field: "stringRepresentation", order: "ASC" },
    },
    { enabled: ownerId !== undefined && signedIn },
  );

  if (ownerId === undefined) {
    return hintWhenAbsent ? (
      <Labeled label={translate("serviceShow.owner")}>
        <Typography variant="body2" color="text.secondary">
          {translate("serviceShow.ownerNone")}
        </Typography>
      </Labeled>
    ) : null;
  }
  if (!signedIn) {
    return null;
  }

  const row = (answer: string, muted = false) => (
    <Labeled label={translate("serviceShow.owner")}>
      <Typography
        variant="body2"
        color={muted ? "text.secondary" : undefined}
      >
        {answer}
      </Typography>
    </Labeled>
  );

  const organization = (data ?? []).find(
    (candidate) => String(candidate.id) === ownerId,
  );
  if (organization !== undefined) {
    return row(defaultRecordRepresentation(organization));
  }
  // The name is not among the organizations this caller may read - a refused
  // list or a page which does not reach that far. It is not the same answer as
  // "no owner is stored" and must not be presented as one.
  if (error || !isPending) {
    return row(translate("serviceShow.ownerUnavailable"), true);
  }
  return null;
};

export default ServiceOwnerField;

import { Link, useCreatePath, useFieldValue, useGetOne } from "react-admin";

export interface RelatedResourceFieldProps {
  source?: string;
}

interface RelatedResource {
  type?: string;
  id?: string;
}

/**
 * Shows the resource a record reports about, which the api addresses by type
 * and id.
 *
 * A background process names its resource with a generic relation, so the
 * answer of the api carries the type and the id of that resource and this field
 * turns them into a link to it. The name of the resource is asked for
 * separately, because the process only knows its type and id.
 */
const RelatedResourceField = ({
  source = "relatedResource",
}: RelatedResourceFieldProps) => {
  const related = useFieldValue({ source }) as RelatedResource | undefined;
  const type = related?.type;
  const id = related?.id;
  const createPath = useCreatePath();
  const { data } = useGetOne(
    type ?? "BackgroundProcess",
    { id: id ?? "" },
    { enabled: Boolean(type && id) },
  );

  if (!type || !id) {
    return null;
  }

  return (
    <Link to={createPath({ resource: type, type: "show", id })}>
      {data?.stringRepresentation ?? `${type} #${id}`}
    </Link>
  );
};

export default RelatedResourceField;

/**
 * Route entry of the full screen record editor (#1245).
 *
 * `:type` is the JSON:API resource name — the same name the resource
 * registration uses — and only counts as a record kind when the OpenAPI
 * schema answers a `retrieve_<type>` operation for it. Anything else is the
 * react-admin 404, the same answer a wrong resource id in the URL gets; the
 * editor itself never re-checks the name against a hardcoded list.
 */

import { NotFound } from "react-admin";
import { useParams } from "react-router-dom";

import useOperation from "../../../../jsonapi/hooks/useOperation";
import MetadataEditor from "./MetadataEditor";

const MetadataEditorRoute = () => {
  const { type, id } = useParams<{ type?: string; id?: string }>();
  const operation = useOperation(type ? `retrieve_${type}` : undefined);
  if (!type || !id || !operation) return <NotFound />;
  // one editor instance per record: switching records must not carry the
  // active section, the findings or the dirty state of the previous one over
  return <MetadataEditor key={`${type}:${id}`} type={type} />;
};

export default MetadataEditorRoute;

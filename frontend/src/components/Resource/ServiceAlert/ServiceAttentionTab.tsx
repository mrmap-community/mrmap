import { useMemo, type ReactNode } from "react";
import {
  ResourceContext,
  useRecordContext,
  useResourceContext,
} from "react-admin";
import type { RelatedResource } from "../../../providers/dataProvider";
import ListServiceAlert from "./ListServiceAlert";

/**
 * Tab which lists the attention the shown service needs.
 *
 * The alerts of a service are answered by the endpoint of the service itself, so
 * this tab only has to name the service it is shown for.
 */
export const ServiceAttentionTab = (): ReactNode => {
  const resource = useResourceContext();
  const record = useRecordContext();

  const relatedResource = useMemo<RelatedResource | undefined>(() => {
    if (resource !== undefined && record !== undefined) {
      return { resource, id: record.id };
    }
  }, [resource, record]);

  return (
    <ResourceContext value="ServiceAlert">
      <ListServiceAlert relatedResource={relatedResource} />
    </ResourceContext>
  );
};

export default ServiceAttentionTab;

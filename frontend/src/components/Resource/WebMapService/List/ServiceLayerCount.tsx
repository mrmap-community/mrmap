import type { Identifier } from "react-admin";
import { Count } from "../../../../jsonapi/components/Count";

export interface ServiceLayerCountProps {
  /** the service the layers are counted of */
  serviceId?: Identifier;
}

/**
 * How many layers a service has.
 *
 * The layers of a service are answered by the api as the layers related to that
 * service, so the count of that list is the count of the layers of the service.
 * Asked like every other count of the frontend: one record of the list, only
 * its id and the number the api answers with it.
 */
const ServiceLayerCount = ({ serviceId }: ServiceLayerCountProps) => {
  if (serviceId === undefined) {
    return null;
  }
  return (
    <Count
      resource="Layer"
      relatedResource="WebMapService"
      relatedResourceId={serviceId}
      variant="body2"
    />
  );
};

export default ServiceLayerCount;

import { type ListProps } from "react-admin";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { type ServiceListConfig } from "./config";
import { serviceListProps } from "./serviceListProps";

export interface ServiceListProps extends Partial<ListProps> {
  /** what differs of this list from the list of the other kind of service */
  config: ServiceListConfig;
}

/**
 * The screen which lists the registered services of one kind of service.
 *
 * This shell hands the configured props to the generic list of the resource; a
 * resource which answers create and edit dialogs on its list uses the
 * ListWithDialogs with the same props instead of this shell.
 */
const ServiceList = ({ config, ...props }: ServiceListProps) => (
  <ListGuesser {...props} {...serviceListProps(config)} />
);

export default ServiceList;

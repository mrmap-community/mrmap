import { useLocaleState, useResourceContext, useTranslate, type ListProps } from "react-admin";

import { Box, Stack, Typography } from "@mui/material";

import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { type ServiceListConfig } from "./config";
import { serviceListProps } from "./serviceListProps";
import ServiceSummaryTiles from './ServiceSummaryTiles';



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

const ServiceHeader = () => {
  const translate = useTranslate()
  const resource = useResourceContext()
  return (
    <Stack spacing={2} sx={{ mx: 2, minWidth: 0 }}>
      <Box>
        <Typography variant="h4" >
            {translate(`resources.${resource}.plural`)}
        </Typography>
        <Typography color="textSecondary" >
          {translate(`resources.${resource}.listSubheader`)}
        </Typography>
      </Box>
      <ServiceSummaryTiles />
    </Stack>
  );
};


const ServiceList = ({ config, ...props }: ServiceListProps) => {
  const [locale] = useLocaleState();

  return (
      <ListGuesser 
        {...props} 
        {...serviceListProps(config, locale)}
        header={<ServiceHeader/>}
      />
  )
};

export default ServiceList;

import { useLocaleState, useResourceContext, useTranslate, type ListProps } from "react-admin";

import { Box, Stack, Typography } from "@mui/material";

import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs";
import { harvestFacetsFor } from "./alertFacets";
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
 * Keep the create and edit dialog routes mounted beside the configured list.
 */

const ServiceHeader = ({ config }: { config: ServiceListConfig }) => {
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
      {/* the tiles of the harvesting are counted where the resource declares the
          filters of the harvesting - the same answer which gives the facets */}
      <ServiceSummaryTiles harvestFacets={harvestFacetsFor(config.harvestFilters)} />
    </Stack>
  );
};


const ServiceList = ({ config, ...props }: ServiceListProps) => {
  const [locale] = useLocaleState();

  return (
      <ListWithDialogs
        listGuesserProps={{
          ...props,
          ...serviceListProps(config, locale),
          header: <ServiceHeader config={config} />,
        }}
      />
  )
};

export default ServiceList;

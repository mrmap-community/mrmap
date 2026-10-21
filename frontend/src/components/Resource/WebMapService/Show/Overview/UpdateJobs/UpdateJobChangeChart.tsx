

  import { useState } from 'react';

import BarChartIcon from '@mui/icons-material/BarChart';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Collapse, IconButton, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import { format, parseISO } from 'date-fns';
import { useGetList, useRecordContext, useTranslate } from 'ra-core';


export const LayerChangesChart = ({ resource }: { resource: string }) => {
  const theme = useTheme();
  const translate = useTranslate();
  const isWfs = resource === "WebFeatureServiceUpdateJob";
  const [expanded, setExpanded] = useState(false);

  const {data: statisticalChanges} = useGetList(
    isWfs ? "StatisticalFeatureTypePerService" : "StatisticalLayerPerService",
    {
      filter: {
        service: useRecordContext()?.id,
      },
      //pagination: { page: 1, perPage: 1 },
      sort: { field: "id", order: "DESC" },
    }
  )


  return (
    <Box>
      <Stack
        direction="row"
        
        spacing={1}
        sx={{
          alignItems:"center",
          px: 2,
          py: 1,
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(value => !value)}
      >
        <BarChartIcon fontSize="small" />

        <Typography
          variant="subtitle2"
          sx={{ flex: 1 }}
        >
          {translate(`serviceShow.${isWfs ? "featureTypeChangesOverTime" : "layerChangesOverTime"}`)}
        </Typography>

        <IconButton size="small">
          {expanded
            ? <ExpandLessIcon fontSize="small" />
            : <ExpandMoreIcon fontSize="small" />
          }
        </IconButton>
      </Stack>

      <Collapse in={expanded}>
        <Box
          sx={{
            px: 1,
            pb: 1,
            height: 160,
          }}
        >
    <BarChart
      dataset={statisticalChanges??[]}
      height={150}
      xAxis={[
        {
          scaleType: 'band',
          dataKey: 'id',
          valueFormatter: (value: string) =>
            format(parseISO(value), 'MMM d'),
        },
      ]}
      yAxis={[
        {
          label: translate(`serviceShow.${isWfs ? "featureTypes" : "layers"}`),
          min: 0,
        },
      ]}
      series={[
        {
          dataKey: 'new',
          label: 'Added',
          stack: 'changes',
          color: theme.palette.success.main,
        },
        {
          dataKey: 'updated',
          label: 'Modified',
          stack: 'changes',
          color:  theme.palette.info.main,
        },
        {
          dataKey: 'deleted',
          label: 'Removed',
          stack: 'changes',
          color: theme.palette.error.main,
        },
      ]}
      margin={{
        left: 45,
        right: 10,
        top: 10,
        bottom: 25,
      }}
      slotProps={{
        legend: {
          position: {
            vertical: 'top',
            horizontal: 'end',
          },
        },
      }}
    />
    </Box>
      </Collapse>
    </Box>
  );
};


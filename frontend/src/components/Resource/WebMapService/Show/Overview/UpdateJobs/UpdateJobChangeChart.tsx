

  import BarChartIcon from '@mui/icons-material/BarChart';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Collapse, IconButton, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import { format, parseISO } from 'date-fns';
import { useGetList, useRecordContext } from 'ra-core';
import { useState } from 'react';


export const LayerChangesChart = () => {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(false);

  const {data: statisticalLayers} = useGetList(
    "StatisticalLayerPerService",
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
          Layer changes over time
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
      dataset={statisticalLayers??[]}
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
          label: 'Layers',
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


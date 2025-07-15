import Box from '@mui/material/Box';
import CircularProgress, {
  CircularProgressProps,
} from '@mui/material/CircularProgress';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';

const CircularProgressWithLabel = (
  props: CircularProgressProps & { 
    value: number,
    tooltip: string
  },
) => {
  return (
    <Tooltip title={props.tooltip}>
      <Box sx={{ position: 'relative', display: 'inline-flex' }}>
        <CircularProgress variant="determinate" {...props} />
        <Box
          sx={{
            top: 0,
            left: 0,
            bottom: 0,
            right: 0,
            position: 'absolute',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography
            variant="caption"
            component="div"
            sx={{ color: 'text.secondary' }}
          >{`${Math.round(props.value)}%`}</Typography>
        </Box>
      </Box>
    </Tooltip>
  );
};

export default CircularProgressWithLabel;

import { alpha, useTheme } from '@mui/material/styles';
import { AreaPlot, ChartContainer, ChartContainerProps, ChartsLegend, ChartsTooltip, LineHighlightPlot, LinePlot } from '@mui/x-charts';


const GradientChartContainer = ({...props}: ChartContainerProps)=>{
  const theme = useTheme();
  
  return (
    <ChartContainer
        yAxis={[{
          width: 30,
          position: 'none'
        }]}
        margin={{ top: 5, bottom: 0, right: 0, left: 0 }}
        sx={{
          '& .MuiAreaElement-series-stats': { fill: "url('#defaultGradiant')", strokeWidth: 2, opacity: 0.8 }
        }}
        {...props}
      >
        <defs>
          <linearGradient id="defaultGradiant" gradientTransform="rotate(90)">
            <stop offset="10%" stopColor={alpha(theme.palette.primary.main, 0.4)} />
            <stop offset="90%" stopColor={alpha(theme.palette.background.default, 0.4)} />
          </linearGradient>
        </defs>
        <AreaPlot />
        <LinePlot />
        <LineHighlightPlot />
        <ChartsLegend direction="horizontal" />
        <ChartsTooltip />
    </ChartContainer >
  )
}


export default GradientChartContainer;
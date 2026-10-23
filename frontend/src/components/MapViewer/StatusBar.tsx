import { useTranslate } from 'react-admin';

import ArticleIcon from '@mui/icons-material/Article';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Box, Stack, Tooltip, Typography } from "@mui/material";

import { getUnsupportedReasons, unsupportedReasonLabel } from '../../ows-lib/OwsContext/capabilities';
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useMapViewerBase } from './MapViewerBase';

const StatusBar = () => {
  const translate = useTranslate()
  const { loadingStatus, loadingMessage, loadingTimings } = useOwsContextBase()
  const { mapLoading, unsupportedFeatures } = useMapViewerBase()
  const mapErrorMessage = Object.values(mapLoading.errors)[0]?.message
  const effectiveStatus = mapLoading.status === 'error' || mapLoading.status === 'loading'
    ? mapLoading.status
    : loadingStatus

  const statusIcon = (() => {
    switch (effectiveStatus) {
      case 'fetching':
      case 'loading':
        return <CloudDownloadIcon fontSize="small" />
      case 'reading':
        return <ArticleIcon fontSize="small" />
      case 'parsing':
        return <AutoFixHighIcon fontSize="small" />
      case 'ready':
        return <CheckCircleOutlineOutlinedIcon fontSize="small" color="success" />
      case 'error':
        return <ErrorOutlineOutlinedIcon fontSize="small" color="error" />
      default:
        return <HourglassEmptyIcon fontSize="small" color="disabled" />
    }
  })()

  const statusText = (() => {
    if (mapLoading.status === 'error') {
      return mapErrorMessage || 'Map load error'
    }
    if (loadingStatus === 'idle') {
      return 'Ready'
    }
    if (loadingStatus === 'error') {
      return loadingMessage || 'Load error'
    }
    return loadingMessage ? `${loadingMessage}` : 'Loading...'
  })()

  const timingEntries = [
    ...Object.entries(loadingTimings ?? {}),
    ...Object.entries(mapLoading.timings).map(([key, value]) => [`map:${key}`, value] as const)
  ].length > 0
    ? [
      ...Object.entries(loadingTimings ?? {}),
      ...Object.entries(mapLoading.timings).map(([key, value]) => [`map:${key}`, value] as const)
    ].map(([key, value]) => ({
        key,
        value: `${typeof value === 'number' ? Math.round(value) : value}ms`
      }))
    : []

  return (
    <Stack
      sx={{ 
        width: '100%', 
        px: 1, 
        py: 0.5,
        direction:"row",
        justifyContent:"space-between",
        alignItems: "center", 
        spacing: 1,
      }}>
      <Stack
        sx={{
          direction: "row",
          alignItems: "center",
          spacing: 1
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', color: effectiveStatus === 'error' ? 'error.main' : 'text.primary' }}>
          {statusIcon}
        </Box>
        <Typography variant="body2" color={effectiveStatus === 'error' ? 'error.main' : 'text.primary'}>
          {mapLoading.status === 'loading'
            ? `Loading map (${mapLoading.loaded}/${mapLoading.total})`
            : statusText}
        </Typography>
      </Stack>

      {unsupportedFeatures.length > 0 && (
        <Tooltip
          title={
            <Stack spacing={0.5}>
              {unsupportedFeatures.map(feature => (
                <Typography variant="caption" key={`${feature.id}:${feature.properties.folder}`}>
                  {feature.properties.title}: {' '}
                  {getUnsupportedReasons(feature)
                    .map(reason => unsupportedReasonLabel(reason, translate))
                    .join(', ')}
                </Typography>
              ))}
            </Stack>
          }
        >
          <Stack direction="row" spacing={0.5} sx={{ cursor: 'default', minWidth: 0, alignItems: 'center' }}>
            <WarningAmberIcon fontSize="small" color="warning" />
            <Typography variant="body2" color="warning.main" noWrap>
              {translate('viewerUnsupported.summary', { count: unsupportedFeatures.length })}
            </Typography>
          </Stack>
        </Tooltip>
      )}

      {timingEntries.length > 0 ? (
        <Stack component="ul" spacing={0.5} sx={{ listStyle: 'none', m: 0, p: 0, width: '100%', maxWidth: 240 }}>
          {timingEntries.map(({ key, value }) => (
            <Box
              component="li"
              key={key}
              sx={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, max-content) minmax(0, 1fr)',
                columnGap: 1,
                alignItems: 'center'
              }}
            >
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', pr: 1 }}>
                {key}:
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                {value}
              </Typography>
            </Box>
          ))}
        </Stack>
      ) : (
        <Box />
      )}
    </Stack>
  )
} 

export default StatusBar
import type { OfferingDimension } from '../../../ows-lib/OwsContext/types';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslate } from 'react-admin';

import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';
import { Box, Button, IconButton, Slider, Stack, TextField, Typography } from '@mui/material';
import moment from 'moment';

import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { getTimeDimensionAxis, getWmsDimensionSelection, isAllowedDimensionValue, parseAdvertisedValues, setWmsDimension } from '../../../ows-lib/OwsContext/dimensions';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import { useMapViewerBase } from '../../MapViewer/MapViewerBase';
import { useContextMenuBase } from './ContextMenuBase';
import ContextMenuItem from './ContextMenuItem';

export const WmsTimeControl = ({ dimension, selection, apply, folder, compact = false, horizontal = false }: {
  dimension: OfferingDimension; selection: string; apply: (value: string) => void; folder?: string; compact?: boolean; horizontal?: boolean;
}) => {
  const translate = useTranslate();
  const { displayedTimes = {}, mapLoading, animation, setAnimation } = useMapViewerBase();
  const axis = useMemo(() => getTimeDimensionAxis(dimension), [dimension.name, dimension.units, dimension.values]);
  const [draft, setDraft] = useState<number>();
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { setDraft(undefined); setInvalid(false); }, [selection]);
  const selectedIndex = axis?.indexOf(selection) ?? -1;
  const defaultIndex = axis?.indexOf(dimension.default ?? '') ?? -1;
  const index = draft ?? (selectedIndex >= 0 ? selectedIndex : defaultIndex >= 0 ? defaultIndex : (axis?.count ?? 1) - 1);
  const preview = draft === undefined ? selection : axis?.valueAt(index) ?? selection;
  const format = (value: string, short = false) => moment.utc(value, moment.ISO_8601, true).isValid() ? moment.utc(value).format(short ? 'DD MMM YYYY HH:mm' : 'DD MMM YYYY · HH:mm [UTC]') : value;
  const label = `${translate('viewerDimensions.dimension', { name: dimension.name })}${dimension.units ? ` (${dimension.units})` : ''} · UTC`;
  const commit = (position: number) => { if (axis) { setDraft(undefined); apply(axis.valueAt(position)); } };

  // playback advances through the advertised times of this very axis; a selected frame which the
  // map has not drawn yet holds the animation on pace, and a frame the service refused is stepped
  // over rather than waited for — the old image stays visible and the status bar carries the
  // error (#705)
  const playing = animation !== undefined && folder !== undefined && animation.folder === folder;
  const fps = animation?.fps ?? 2;
  const loop = animation?.loop ?? false;
  const displayedTime = folder !== undefined ? displayedTimes[folder] : undefined;
  const failed = folder !== undefined && (mapLoading?.failedFeatures ?? []).some(feature => feature.properties.folder === folder);
  const pending = displayedTime !== undefined && selection !== '' && displayedTime !== selection && !failed;
  // where playback continues from: the selected position, or the advertised default, or -1 so
  // that playback from the server default begins with the first advertised observation
  const from = selectedIndex >= 0 ? selectedIndex : defaultIndex;
  // a fast interval can fire several times before the render which carries the applied time
  // arrives: the tick judges the pending frame by the time it applied itself, read from refs,
  // so no frame is advanced from a stale selection and none is queued behind a slow render
  const appliedRef = useRef<string | undefined>(undefined);
  const liveRef = useRef({ selection, displayedTime, failed, loop, from, axis, apply });
  liveRef.current = { selection, displayedTime, failed, loop, from, axis, apply };
  useEffect(() => { appliedRef.current = undefined; }, [selection]);
  useEffect(() => {
    if (!playing || !axis || axis.count < 2) return;
    const timer = setInterval(() => {
      const live = liveRef.current;
      const current = appliedRef.current ?? live.selection;
      if (live.displayedTime !== undefined && current !== '' && live.displayedTime !== current && !live.failed) return;
      const position = axis.indexOf(current);
      const next = (position >= 0 ? position : live.from) + 1;
      if (next < axis.count) { appliedRef.current = axis.valueAt(next); live.apply(axis.valueAt(next)); }
      else if (live.loop) { appliedRef.current = axis.valueAt(0); live.apply(axis.valueAt(0)); }
      else {
        // end of the advertised range: playback stops there, and pressing play again starts it
        // from the first observation
        setAnimation(undefined);
      }
    }, 1000 / fps);
    return () => clearInterval(timer);
  }, [playing, fps, axis, setAnimation]);
  // the animation belongs to the mounted control: closing the panel or removing the layer ends
  // it, so no playback stays flagged in the session for a control which is gone
  const leaveRef = useRef<() => void>(() => undefined);
  leaveRef.current = () => { if (playing) setAnimation(undefined); };
  useEffect(() => () => leaveRef.current(), []);
  const togglePlay = () => {
    if (playing) { setAnimation(undefined); return; }
    if (failed && axis) {
      // playback stopped at a frame the service refused: starting again steps over it
      const next = from + 1;
      const value = axis.valueAt(next < axis.count ? next : 0);
      appliedRef.current = value;
      apply(value);
    }
    setAnimation({ folder: folder ?? '', fps, loop });
  };
  return <Box sx={{ minWidth: 0, display: 'grid', gridTemplateColumns: horizontal ? 'repeat(auto-fit, minmax(min(100%, 180px), 1fr))' : 'minmax(0, 1fr)', gap: horizontal ? 2 : 1, alignItems: 'start' }}>
    <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0, width: '100%' }}>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere' }}>{format(preview) || translate('viewerDimensions.serverDefault')}</Typography>
    {axis && <>
      <Slider aria-label={label} min={0} max={Math.max(1, axis.count - 1)} step={1} shiftStep={10}
        disabled={axis.count < 2} value={index} valueLabelDisplay="auto"
        getAriaValueText={position => axis.valueAt(Math.min(position, axis.count - 1))}
        valueLabelFormat={position => format(axis.valueAt(Math.min(position, axis.count - 1)))}
        onChange={(_, value) => setDraft(value as number)}
        onChangeCommitted={(_, value) => commit(value as number)}
        sx={{ width: 'calc(100% - 24px)', mx: '12px', '& .MuiSlider-valueLabel': { fontSize: 11 } }} />
      <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 0, fontSize: 10 }}>{format(axis.valueAt(0), true)}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 0, textAlign: 'right', fontSize: 10 }}>{format(axis.valueAt(axis.count - 1), true)}</Typography>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <IconButton size="small" sx={{ minWidth: 28 }} aria-label={translate(playing ? 'viewerDimensions.pause' : 'viewerDimensions.play')} onClick={togglePlay} disabled={axis.count < 2}>{playing ? '❚❚' : '▶'}</IconButton>
        <Button size="small" sx={{ minWidth: 28 }} aria-label={translate('ra.navigation.previous')} disabled={index === 0} onClick={() => commit(index - 1)}>‹</Button>
        <Button size="small" sx={{ minWidth: 28 }} aria-label={translate('ra.navigation.next')} disabled={index >= axis.count - 1} onClick={() => commit(index + 1)}>›</Button>
        <IconButton size="small" sx={{ minWidth: 28 }} aria-label={translate('viewerDimensions.loop')} aria-pressed={loop} disabled={!playing} onClick={() => setAnimation({ folder: folder ?? '', fps, loop: !loop })}>{'\u21BA'}</IconButton>
        <TextField select size="small" value={fps} disabled={!playing} onChange={event => setAnimation({ folder: folder ?? '', fps: Number(event.target.value), loop })}
          sx={{ width: 88 }} slotProps={{ select: { native: true, 'aria-label': translate('viewerDimensions.speed') } }}>
          {[0.5, 1, 2, 4].map(rate => <option key={rate} value={rate}>{translate('viewerDimensions.speedValue', { fps: rate })}</option>)}
        </TextField>
        <Typography variant="caption" sx={{ alignSelf: 'center' }}>{translate('viewerDimensions.position', { current: new Intl.NumberFormat(undefined, { notation: axis.count > 10000 ? 'compact' : 'standard' }).format(index + 1), total: new Intl.NumberFormat(undefined, { notation: axis.count > 10000 ? 'compact' : 'standard' }).format(axis.count) })}</Typography>
      </Stack>
      {pending && <Typography variant="caption" color="text.secondary">{translate('viewerDimensions.displaying', { time: format(displayedTime!, true) })}</Typography>}
    </>}
    </Stack>
    <Stack spacing={1} sx={{ width: '100%', minWidth: 0 }}>
    {!compact && <TextField key={selection} fullWidth type="datetime-local" label={label}
      sx={theme => ({ '& input': { colorScheme: theme.palette.mode } })}
      defaultValue={moment.utc(selection, moment.ISO_8601, true).isValid() ? moment.utc(selection).format('YYYY-MM-DDTHH:mm:ss.SSS') : ''}
      slotProps={{ inputLabel: { shrink: true }, htmlInput: { step: 'any' } }}
      error={invalid} helperText={invalid ? translate('viewerDimensions.invalid') : translate('viewerDimensions.sliderHint')}
      onBlur={event => {
        const parsed = moment.utc(event.target.value, moment.ISO_8601, true);
        const normalized = parsed.isValid() ? parsed.toISOString() : event.target.value;
        const position = axis?.indexOf(normalized) ?? -1;
        const value = event.target.value === '' ? '' : position >= 0 && axis ? axis.valueAt(position) : normalized;
        const allowed = isAllowedDimensionValue(dimension, value);
        setInvalid(!allowed);
        if (allowed) { setDraft(undefined); apply(value); }
      }} />}
    <Button size="small" onClick={() => { setDraft(undefined); setInvalid(false); apply(''); }}>{translate('viewerDimensions.serverDefault')}</Button>
  </Stack>
  </Box>;
};

export const WmsDimensionControls = ({ folder, inline = false, timeOnly = false, compact = false, horizontal = false }: { folder?: string; inline?: boolean; timeOnly?: boolean; compact?: boolean; horizontal?: boolean }) => {
  const { owsContext, setOwsContext } = useOwsContextBase()
  const translate = useTranslate()
  const [invalid, setInvalid] = useState<Record<string, boolean>>({})
  const node = owsContext.findResourceByFolder(folder)
  const offering = node?.getWmsOffering()
  const dimensions = (offering?.dimensions ?? []).filter(dimension => !timeOnly || /^(?:dim_)?time$/i.test(dimension.name) || dimension.units === 'ISO8601')
  const layerTitle = node ? [...owsContext.getAncestorsOf(node), node].map(item => item.properties.title).join(' / ') : undefined

  const apply = (name: string, value: string) => {
    const next = OWSContext.fromPlainObject(owsContext)
    const target = next.findResourceByFolder(folder)?.getWmsOffering()
    if (!target) return
    setWmsDimension(target, name, value)
    setOwsContext(next)
  }

  if (dimensions.length === 0) return <Stack spacing={1} sx={{ py: 1 }}>
    {layerTitle && <Typography variant="body2" color="text.secondary">{layerTitle}</Typography>}
    <Typography>{translate('viewerDimensions.none')}</Typography>
  </Stack>

  return <Stack spacing={3} sx={{ minWidth: 0, py: 1 }}>
    {!inline && <Typography variant="body2" color="text.secondary">{layerTitle}</Typography>}
    {dimensions.map(dimension => {
      const advertised = parseAdvertisedValues(dimension.values)
      const selection = getWmsDimensionSelection(offering!, dimension)
      const label = `${translate('viewerDimensions.dimension', { name: dimension.name })}${dimension.units ? ` (${dimension.units})` : ''}`
      if (advertised.kind === 'time-range' || getTimeDimensionAxis(dimension)) {
        return <WmsTimeControl key={dimension.name} dimension={dimension} selection={selection} apply={value => apply(dimension.name, value)} folder={folder} compact={compact} horizontal={horizontal} />
      }
      if (advertised.kind === 'range') {
        const hint = `${advertised.start} … ${advertised.stop}${advertised.step !== undefined ? ` · ${advertised.step}` : ''}`
        return <TextField
          key={`${dimension.name}:${selection}`}
          type="number"
          fullWidth
          label={label}
          defaultValue={selection}
          slotProps={{ inputLabel: { shrink: true } }}
          error={invalid[dimension.name] === true}
          helperText={invalid[dimension.name] ? translate('viewerDimensions.invalid') : hint}
          onChange={event => {
            const value = event.target.value
            if (!isAllowedDimensionValue(dimension, value)) {
              setInvalid(current => ({ ...current, [dimension.name]: true }))
              return
            }
            setInvalid(current => ({ ...current, [dimension.name]: false }))
            apply(dimension.name, value)
          }}
        />
      }
      return <TextField
        key={`${dimension.name}:${selection}`}
        select
        fullWidth
        label={label}
        value={selection}
        slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
        onChange={event => apply(dimension.name, event.target.value)}
      >
        <option value="">{translate('viewerDimensions.serverDefault')}</option>
        {dimension.default !== undefined && !advertised.values.includes(dimension.default) && <option value={dimension.default}>{dimension.default}</option>}
        {selection !== '' && selection !== dimension.default && !advertised.values.includes(selection) && <option value={selection} disabled>{selection}</option>}
        {advertised.values.map(value => <option key={value} value={value}>{value}</option>)}
      </TextField>
    })}
  </Stack>
}

const DimensionItem = () => {
  const translate = useTranslate();
  const { node, close, setControlsId } = useContextMenuBase();
  if (!node?.getWmsOperationByCode('GetMap') && !node?.getWmsOperationByCode('GetFeatureInfo')) return null;

  return <ContextMenuItem
    disabled={(node?.getWmsOffering()?.dimensions?.length ?? 0) === 0}
    icon={<TuneOutlinedIcon fontSize="small" />}
    label={translate('viewerDimensions.title')}
    onClick={() => {
      setControlsId(node.id);
      close();
    }}
  />;
};

export default DimensionItem;

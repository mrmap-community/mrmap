import { useState } from 'react';
import { useTranslate } from 'react-admin';

import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';
import { Button, Stack, TextField, Typography } from '@mui/material';

import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { getWmsDimensionSelection, isAllowedDimensionValue, parseAdvertisedValues, setWmsDimension } from '../../../ows-lib/OwsContext/dimensions';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import { useDialogContextBase } from '../../Dialog/DialogContextBase';
import DialogHeader from '../../Dialog/DialogHeader';
import { useContextMenuBase } from './ContextMenuBase';
import ContextMenuItem from './ContextMenuItem';

export const WmsDimensionControls = ({ folder }: { folder?: string }) => {
  const { owsContext, setOwsContext } = useOwsContextBase()
  const translate = useTranslate()
  const [invalid, setInvalid] = useState<Record<string, boolean>>({})
  const node = owsContext.findResourceByFolder(folder)
  const offering = node?.getWmsOffering()
  const dimensions = offering?.dimensions ?? []
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
    <Typography variant="body2" color="text.secondary">{layerTitle}</Typography>
    {dimensions.map(dimension => {
      const advertised = parseAdvertisedValues(dimension.values)
      const selection = getWmsDimensionSelection(offering!, dimension)
      const label = `${translate('viewerDimensions.dimension', { name: dimension.name })}${dimension.units ? ` (${dimension.units})` : ''}`
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

const DimensionActions = () => {
  const { close } = useDialogContextBase();
  const translate = useTranslate();
  return <Stack direction="row" sx={{ width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
    <Typography variant="caption" color="text.secondary">{translate('viewerStyles.immediate')}</Typography>
    <Button onClick={close}>{translate('viewerStyles.done')}</Button>
  </Stack>;
};

const DimensionItem = () => {
  const translate = useTranslate();
  const { node, close } = useContextMenuBase();
  const { open } = useDialogContextBase();
  if (!node?.getWmsOperationByCode('GetMap') && !node?.getWmsOperationByCode('GetFeatureInfo')) return null;

  return <ContextMenuItem
    disabled={(node?.getWmsOffering()?.dimensions?.length ?? 0) === 0}
    icon={<TuneOutlinedIcon fontSize="small" />}
    label={translate('viewerDimensions.title')}
    onClick={() => {
      open(
        <DialogHeader>{translate('viewerDimensions.title')}</DialogHeader>,
        <WmsDimensionControls folder={node?.properties.folder} />,
        <DimensionActions />,
      );
      close();
    }}
  />;
};

export default DimensionItem;

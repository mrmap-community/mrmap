import { useId } from 'react';
import { useTranslate } from 'react-admin';

import PaletteOutlinedIcon from '@mui/icons-material/PaletteOutlined';
import { Button, Stack, TextField, Typography } from '@mui/material';

import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { getWmsOperationStyles, setWmsLayerStyle } from '../../../ows-lib/OwsContext/utils';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import { useDialogContextBase } from '../../Dialog/DialogContextBase';
import DialogHeader from '../../Dialog/DialogHeader';
import { PreviewImage } from '../../Resource/Generic/ServiceShow/ServicePreviewImage';
import { useContextMenuBase } from './ContextMenuBase';
import ContextMenuItem from './ContextMenuItem';

const WmsStyleControls = ({ folder }: { folder?: string }) => {
  const { owsContext, setOwsContext } = useOwsContextBase()
  const translate = useTranslate()
  const id = useId()
  const node = owsContext.findResourceByFolder(folder)
  const layerTitle = node ? [...owsContext.getAncestorsOf(node), node].map(item => item.properties.title).join(' / ') : undefined
  const offering = node?.getWmsOffering()
  const selections = getWmsOperationStyles(node?.getWmsOperationByCode('GetMap') ?? node?.getWmsOperationByCode('GetFeatureInfo'))
  const styles = offering?.styles?.filter(style => style.name.trim() !== '') ?? []

  return <Stack spacing={3} sx={{ minWidth: 0, py: 1 }}>
    <Typography variant="body2" color="text.secondary">{layerTitle}</Typography>
    {selections.length === 0 && <Typography>{translate('viewerStyles.noStyles')}</Typography>}
    {selections.map(({ layer, style }, index) => {
      const selected = style ? styles.find(item => item.name === style) : styles.find(item => item.default)
      const legend = selected?.legendURL
      const src = legend && /^https?:\/\//i.test(legend) ? legend : undefined
      return <Stack key={`${layer}:${index}`} spacing={1.5}>
        <TextField
          id={`${id}-${index}`}
          select
          fullWidth
          disabled={styles.length === 0}
          helperText={styles.length === 0 ? translate('viewerStyles.noStyles') : undefined}
          label={translate('viewerStyles.style', { layer })}
          value={style}
          slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
          onChange={event => {
            const next = OWSContext.fromPlainObject(owsContext)
            const target = next.findResourceByFolder(folder)?.getWmsOffering()
            if (!target) return
            setWmsLayerStyle(target, layer, event.target.value)
            setOwsContext(next)
          }}
        >
          <option value="">{translate('viewerStyles.default')}</option>
          {style && !styles.some(item => item.name === style) && <option value={style} disabled>{style}</option>}
          {styles.map(item => <option key={item.name} value={item.name}>{item.title || item.name}</option>)}
        </TextField>
        <Typography variant="subtitle2">{translate('viewerStyles.legendTitle')}</Typography>
        <PreviewImage
          key={`${layer}:${style}:${src}`}
          src={src}
          alt={translate('viewerStyles.legend', { layer, style: selected?.title || style || translate('viewerStyles.default') })}
          loadingLabel={translate('viewerStyles.loading')}
          unavailableLabel={translate('viewerStyles.unavailable')}
          containerSx={{ width: { xs: '100%', sm: '100%' }, height: 'auto', minHeight: 96, justifyContent: 'flex-start' }}
          imageSx={{ width: 'auto', height: 'auto', maxWidth: '100%', maxHeight: 240 }}
        />
      </Stack>
    })}
  </Stack>
}

const StyleLegendActions = () => {
  const { close } = useDialogContextBase();
  const translate = useTranslate();
  return <Stack direction="row" sx={{ width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
    <Typography variant="caption" color="text.secondary">{translate('viewerStyles.immediate')}</Typography>
    <Button onClick={close}>{translate('viewerStyles.done')}</Button>
  </Stack>;
};

const StyleLegendItem = () => {
  const translate = useTranslate();
  const { node, close } = useContextMenuBase();
  const { open } = useDialogContextBase();
  if (!node?.getWmsOperationByCode('GetMap') && !node?.getWmsOperationByCode('GetFeatureInfo')) return null;

  return <ContextMenuItem
    icon={<PaletteOutlinedIcon fontSize="small" />}
    label={translate('viewerStyles.title')}
    onClick={() => {
      open(
        <DialogHeader>{translate('viewerStyles.title')}</DialogHeader>,
        <WmsStyleControls folder={node?.properties.folder} />,
        <StyleLegendActions />,
      );
      close();
    }}
  />;
};

export default StyleLegendItem;

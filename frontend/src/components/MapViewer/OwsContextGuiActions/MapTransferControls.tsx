import { useEffect, useRef, useState } from 'react';
import { useTranslate } from 'react-admin';

import DownloadIcon from '@mui/icons-material/Download';
import ShareIcon from '@mui/icons-material/Share';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Fab, Snackbar, TextField, Tooltip, Typography } from '@mui/material';

import { serializeOwsContext } from '../../../ows-lib/OwsContext/authentication';
import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

export const DRAFT_STORAGE_KEY = 'mrmap.mapviewer.draft.v1';
export const SHARE_FRAGMENT_PARAMETER = 'map';

interface PlainOperation { href?: string }
interface PlainOffering { operations?: PlainOperation[] }
interface PlainFeature { properties?: { offerings?: PlainOffering[] } }
interface PlainDocument { features?: PlainFeature[] }

/**
 * The document as it leaves the viewer: secrets redacted by the shared serializer, credentials
 * embedded in operation URLs stripped, and without the runtime folder lookup - so a reopened
 * document rebuilds its tree from the stated folders instead of a derived copy.
 */
export const serializeForTransfer = (context: OWSContext): string => {
  const document = JSON.parse(serializeOwsContext(context)) as PlainDocument;
  for (const feature of document.features ?? []) {
    for (const offering of (feature.properties?.offerings ?? []) as PlainOffering[]) {
      for (const operation of offering.operations ?? []) {
        if (typeof operation.href !== 'string') continue;
        try {
          const url = new URL(operation.href);
          if (url.username === '' && url.password === '') continue;
          url.username = '';
          url.password = '';
          operation.href = url.href;
        } catch {
          // an href the browser cannot parse stays as the document states it
        }
      }
    }
  }
  return JSON.stringify(document, null, 2);
};

const toBase64Url = (text: string) => {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

const fromBase64Url = (encoded: string) => {
  const binary = atob(encoded.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
};

export const encodeShareFragment = (json: string) => `${SHARE_FRAGMENT_PARAMETER}=${toBase64Url(json)}`;

export const decodeShareFragment = (fragment: string): unknown | undefined => {
  const parameter = fragment.startsWith('#') ? fragment.slice(1) : fragment;
  if (!parameter.startsWith(`${SHARE_FRAGMENT_PARAMETER}=`)) return undefined;
  try {
    return JSON.parse(fromBase64Url(decodeURIComponent(parameter.slice(SHARE_FRAGMENT_PARAMETER.length + 1))));
  } catch {
    return undefined;
  }
};

/**
 * Opens what the location brings to a fresh viewer: a shared document in the URL fragment wins
 * over the locally kept draft of the last session. The fragment is removed after loading, so a
 * reload does not keep replaying the share, and the draft takes effect only while it holds a map.
 */
export const useTransferEntry = ({ persistDrafts = true }: { persistDrafts?: boolean } = {}) => {
  const { owsContext, updateOwsContext, isLoading } = useOwsContextBase();
  const [notice, setNotice] = useState<string | undefined>(undefined);
  const entryDone = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (entryDone.current) return;
    entryDone.current = true;
    const shared = decodeShareFragment(window.location.hash);
    if (shared !== undefined) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
      const result = updateOwsContext(shared);
      if (!result.hasErrors) setNotice('shared');
      return;
    }
    try {
      const draft = window.localStorage.getItem(DRAFT_STORAGE_KEY);
      if (draft === null || draft.trim() === '') return;
      const parsed: unknown = JSON.parse(draft);
      const features = (parsed as PlainDocument | null)?.features;
      if (!Array.isArray(features) || features.length === 0) return;
      const result = updateOwsContext(parsed);
      if (!result.hasErrors) setNotice('draft');
    } catch {
      // a broken draft is dropped silently; the next save overwrites it
    }
  }, [updateOwsContext]);

  useEffect(() => {
    if (!persistDrafts || isLoading) return;
    if (saveTimer.current !== undefined) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      try {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, serializeForTransfer(owsContext));
      } catch {
        // a full or blocked storage must not break the viewer
      }
    }, 500);
    return () => {
      if (saveTimer.current !== undefined) clearTimeout(saveTimer.current);
    };
  }, [owsContext, isLoading, persistDrafts]);

  return { notice, dismissNotice: () => setNotice(undefined) };
};

export const MapTransferControls = ({ persistDrafts = true }: { persistDrafts?: boolean }) => {
  const translate = useTranslate();
  const { owsContext, updateOwsContext } = useOwsContextBase();
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [shareLink, setShareLink] = useState<string | undefined>(undefined);
  const [importErrors, setImportErrors] = useState<string[] | undefined>(undefined);
  const { notice, dismissNotice } = useTransferEntry({ persistDrafts });

  const exportMap = () => {
    const blob = new Blob([serializeForTransfer(owsContext)], { type: 'application/geo+json' });
    const href = URL.createObjectURL(blob);
    const anchor = window.document.createElement('a');
    anchor.href = href;
    anchor.download = `${(owsContext.properties?.title || 'map').replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.geojson`;
    window.document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  };

  const importFile = async (file: File) => {
    try {
      const result = updateOwsContext(JSON.parse(await file.text()));
      if (result.hasErrors)
        setImportErrors(result.issues.filter(issue => issue.severity === 'error').map(issue => `${issue.path}: ${issue.message}`));
      else setImportErrors([]);
    } catch (error) {
      setImportErrors([error instanceof Error ? error.message : String(error)]);
    }
  };

  const shareMap = () => {
    const link = `${window.location.origin}${window.location.pathname}#${encodeShareFragment(serializeForTransfer(owsContext))}`;
    setShareLink(link);
    navigator.clipboard?.writeText(link).catch(() => undefined);
  };

  return <>
    <Tooltip title={translate('mapTransfer.export')}>
      <span><Fab size="small" color="primary" aria-label="export-map" onClick={exportMap}><DownloadIcon /></Fab></span>
    </Tooltip>
    <Tooltip title={translate('mapTransfer.import')}>
      <span>
        <Fab size="small" color="primary" aria-label="import-map" onClick={() => fileInput.current?.click()}><UploadFileIcon /></Fab>
        <input
          ref={fileInput}
          type="file"
          accept=".json,.geojson,application/json,application/geo+json"
          hidden
          onChange={event => {
            const file = event.target.files?.[0];
            if (file !== undefined) void importFile(file);
            event.target.value = '';
          }}
        />
      </span>
    </Tooltip>
    <Tooltip title={translate('mapTransfer.share')}>
      <span><Fab size="small" color="secondary" aria-label="share-map" onClick={shareMap}><ShareIcon /></Fab></span>
    </Tooltip>

    <Snackbar
      open={notice !== undefined}
      autoHideDuration={6000}
      onClose={dismissNotice}
      message={translate(`mapTransfer.restored${notice === 'shared' ? 'Share' : 'Draft'}`)}
    />

    <Dialog open={importErrors !== undefined} onClose={() => setImportErrors(undefined)} maxWidth="sm" fullWidth>
      <DialogTitle>{translate('mapTransfer.import')}</DialogTitle>
      <DialogContent>
        {(importErrors?.length ?? 0) === 0
          ? <Typography>{translate('mapTransfer.importOk')}</Typography>
          : <Alert severity="error">{importErrors!.join('\n')}</Alert>}
        <Typography variant="caption" color="text.secondary">{translate('mapTransfer.credentialsHint')}</Typography>
      </DialogContent>
      <DialogActions><Button onClick={() => setImportErrors(undefined)}>{translate('mapTransfer.close')}</Button></DialogActions>
    </Dialog>

    <Dialog open={shareLink !== undefined} onClose={() => setShareLink(undefined)} maxWidth="sm" fullWidth>
      <DialogTitle>{translate('mapTransfer.share')}</DialogTitle>
      <DialogContent>
        <TextField
          fullWidth
          multiline
          minRows={2}
          slotProps={{ input: { readOnly: true } }}
          value={shareLink ?? ''}
          onFocus={event => event.target.select()}
        />
        <Typography variant="caption" color="text.secondary">{translate('mapTransfer.shareHint')}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { navigator.clipboard?.writeText(shareLink ?? '').catch(() => undefined); }}>{translate('mapTransfer.copy')}</Button>
        <Button onClick={() => setShareLink(undefined)}>{translate('mapTransfer.close')}</Button>
      </DialogActions>
    </Dialog>
  </>;
};

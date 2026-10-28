import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, ButtonProps, RaRecord, useGetOne, useRecordContext, useTranslate } from 'react-admin';
import { useNavigate } from 'react-router-dom';

import PublicIcon from '@mui/icons-material/Public';
import {
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  List,
  ListItemButton,
} from '@mui/material';

import { dropUnassignedAuthentication } from '../../../../ows-lib/OwsContext/authentication';
import { OWSContext } from '../../../../ows-lib/OwsContext/core';
import { prepareGetCapabilititesUrl } from '../../../../ows-lib/OwsContext/utils';
import { getAuthToken } from '../../../../providers/authProvider';
import { useOwsContextBase } from '../../../../react-ows-lib/ContextProvider/OwsContextBase';


export interface WfsMapViewerButtonProps extends ButtonProps {
  wfsRecord?: RaRecord
  capabilititesUrl?: string
  /** The feature type the viewer shall show: it is the one type the map asks for, and the chooser
   *  of the types stays out of the way, because its user already chose this one. */
  element?: RaRecord
}

const sameOrigin = (href: string) => {
  try {
    return new URL(href, window.location.href).origin === window.location.origin
  } catch {
    return false
  }
}

/**
 * The names a feature type answers to: the name as it was written and, for a qualified name, its
 * local part after the namespace prefix - both lowercased. A service announces its types qualified
 * with a namespace ("ms:Countries"), while the database may store them with the local part only
 * ("countries"), and both spellings are the same type; matching them exactly would drop the type.
 */
export const featureTypeAliases = (name: string): string[] =>
  [name, name.split(':').pop() ?? name].map(alias => alias.toLowerCase())

/**
 * Opens a registered Web Feature Service in the viewer: the viewer starts with this service's
 * tree only and the user chooses which feature types the map shall ask for. The credentials of
 * this deployment are handed to the operations of the same origin through the context's own
 * origin-scoped assignment.
 */
const WfsMapViewerButton = ({
  wfsRecord,
  capabilititesUrl,
  element,
  children,
  ...rest
}: WfsMapViewerButtonProps): ReactNode => {
  const navigate = useNavigate();
  const { addWFSByUrl, resetContext, owsContext } = useOwsContextBase()
  const record = useRecordContext(wfsRecord)
  const translate = useTranslate()

  const [clicked, setClicked] = useState(false)
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [confirmed, setConfirmed] = useState(false)

  const { data: wfsRecordWithUrl, isLoading, refetch } = useGetOne(
    "WebFeatureService",
    {
      id: record?.id,
      meta: {
        "jsonApiParams": {
          "include": "operationUrls,featuretypes",
          "fields[WebFeatureService]": "operation_urls,version,featuretypes",
          "fields[WebFeatureServiceOperationUrl]": "url,method,operation",
          "fields[FeatureType]": "identifier,title,is_active",
        }
      }
    },
    {
      enabled: false, // the record with its operation urls is only needed when the button is used
    }
  )

  const getCapabilitiesUrl = capabilititesUrl || wfsRecordWithUrl?.operationUrls?.find(
    (opUrl: RaRecord) => {
      return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation === 1 || opUrl.operation === "GetCapabilities")
    })?.url

  const featureTypes = useMemo<RaRecord[]>(
    () => Array.isArray(wfsRecordWithUrl?.featuretypes) ? wfsRecordWithUrl.featuretypes : [],
    [wfsRecordWithUrl])

  const handleOnClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    setClicked(true)
  }, [])

  // the selection belongs to the record: a new service asks the user again
  useEffect(() => {
    if (clicked && wfsRecordWithUrl === undefined)
      refetch()
    else if (clicked && wfsRecordWithUrl !== undefined && !selecting && !confirmed) {
      // the element the caller named is chosen with its click in the list, so the map asks that one
      // type and the chooser would only ask what is already answered. A type the service does not
      // offer leaves the chooser in charge, because there would be nothing to ask for.
      const named = element === undefined
        ? undefined
        : featureTypes.find(featureType => featureType.id === element.id)
      if (named !== undefined) {
        setSelected([String(named.identifier)])
        setConfirmed(true)
        resetContext()
      } else {
        setSelected(featureTypes.map(featureType => String(featureType.identifier)))
        setSelecting(true)
      }
      setClicked(false)
    }
  }, [clicked, wfsRecordWithUrl, refetch, selecting, confirmed, featureTypes, element, resetContext])

  // the types the user chose become the active types of the freshly appended tree; the database
  // records of the feature types travel with the operations like the WMS layers do, so the tree
  // can answer their metadata without another request
  const beforeSetHook = useCallback((context: OWSContext, treeId: number) => {
    if (getCapabilitiesUrl !== undefined && sameOrigin(getCapabilitiesUrl))
      // the registry served this document, so an operation it advertises on another origin is a
      // public upstream one: the session of the requester is not its credential
      dropUnassignedAuthentication(context, treeId, getCapabilitiesUrl)
    const selectedAliases = new Set(selected.flatMap(featureTypeAliases))
    context.features
      .filter(feature => feature.getWfsOffering() !== undefined)
      .forEach(feature => {
        const operation = feature.getWfsOperationByCode('GetFeature', 'GET')
        if (operation === undefined) return

        operation['x-mrmap-service-id'] = wfsRecordWithUrl?.id
        const request = new URL(operation.href)
        // the types a GetFeature request names, in the singular as in the plural spelling
        const announcedNames = [...request.searchParams.entries()]
          .filter(([key]) => ['typename', 'typenames'].includes(key.toLowerCase()))
          .flatMap(([, value]) => value.split(','))
        const announcedAliases = new Set(announcedNames.flatMap(featureTypeAliases))
        const dbFeatureType = featureTypes.find(
          featureType => featureTypeAliases(String(featureType.identifier))
            .some(alias => announcedAliases.has(alias)))
        if (dbFeatureType !== undefined) {
          operation['x-mrmap-feature-type-id'] = dbFeatureType.id
          operation['x-mrmap-feature-type-properties'] = { ...dbFeatureType }
        }

        // only the chosen types are asked for; the document keeps the rest inactive
        const active = announcedNames.some(
          name => featureTypeAliases(name).some(alias => selectedAliases.has(alias)))
        feature.properties.active = active
        operation.active = active
      })
    return context
  }, [selected, featureTypes, wfsRecordWithUrl, getCapabilitiesUrl])

  const confirm = useCallback(() => {
    setSelecting(false)
    setConfirmed(true)
    resetContext()
  }, [resetContext])

  useEffect(() => {
    if (
      confirmed &&
      wfsRecordWithUrl !== undefined &&
      owsContext.features.length === 0 &&
      getCapabilitiesUrl !== undefined
    ) {
      // wait until the context is empty, then hand this service to the viewer
      const url = prepareGetCapabilititesUrl(getCapabilitiesUrl, 'wfs')
      const token = sameOrigin(getCapabilitiesUrl) ? getAuthToken()?.token : undefined
      addWFSByUrl(
        url.href,
        token ? new Headers({ 'Authorization': `Token ${token}` }) : undefined,
        beforeSetHook
      )
      navigate('/viewer')
      setConfirmed(false)
    }
  }, [confirmed, owsContext, getCapabilitiesUrl, wfsRecordWithUrl, addWFSByUrl, beforeSetHook, navigate])

  return (
    <>
      <Button
        color="primary"
        onClick={handleOnClick}
        label="ra.action.mapviewer"
        loading={isLoading}
        disabled={isLoading}
        {...rest}
      >
        {children || <PublicIcon />}
      </Button>
      <Dialog open={selecting} onClose={() => { setSelecting(false); setClicked(false); }}>
        <DialogTitle>{translate('wfsViewer.selectTitle', {
          service: String(wfsRecordWithUrl?.title ?? record?.title ?? ''),
        })}</DialogTitle>
        <DialogContent>
          <List dense>
            {featureTypes.map(featureType => (
              <ListItemButton
                key={String(featureType.id ?? featureType.identifier)}
                dense
                selected={selected.includes(String(featureType.identifier))}
                onClick={() => setSelected((previous) => previous.includes(String(featureType.identifier))
                  ? previous.filter(name => name !== String(featureType.identifier))
                  : [...previous, String(featureType.identifier)])}
              >
                <FormControlLabel
                  control={<Checkbox
                    checked={selected.includes(String(featureType.identifier))}
                    edge="start"
                    tabIndex={-1}
                    disableRipple
                    // the ListItemButton owns the click; the checkbox only answers visually
                    onClick={(event) => event.stopPropagation()}
                  />}
                  label={`${String(featureType.title ?? featureType.identifier)} (${String(featureType.identifier)})`}
                />
              </ListItemButton>
            ))}
          </List>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setSelecting(false); setClicked(false); }} label="ra.action.cancel" />
          <Button
            onClick={confirm}
            color="primary"
            disabled={selected.length === 0}
            label="ra.action.add"
          />
        </DialogActions>
      </Dialog>
    </>
  )
}

export default WfsMapViewerButton

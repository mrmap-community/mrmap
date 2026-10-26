import { useMemo } from 'react';
import { DeleteButton, RecordRepresentation, SaveButton, useRedirect, useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import { Route, Routes, useParams, useLocation } from 'react-router-dom';

import { DialogProps } from "@mui/material";
import { Fragment } from "react/jsx-runtime";

import ContextBasedDialog from '../../components/Dialog/Dialog';
import DialogHeader from '../../components/Dialog/DialogHeader';
import CreateGuesser, { CreateGuesserProps } from './CreateGuesser';
import EditGuesser, { EditGuesserProps } from "./EditGuesser";
import ListGuesser, { ListGuesserProps } from "./ListGuesser";


const DialogRoute = (
  {
    children,
    open,
    onClose: _onClose,
    ...rest
  }: DialogProps
) => {
  const location = useLocation()
  const { dialogId } = useParams<{ dialogId?: string }>();
  // detect "create" route reliably: check last path segment
  const lastSegment = location.pathname.replace(/\/$/, '').split('/').pop();
  const isCreate = dialogId === 'create' || lastSegment === 'create';
  // Check if the current path has trailing content after the ID
  // Dialog should not open only if: path has content after /show that ends with /show
  // Examples: 
  // - /id/show → open (just show)
  // - /id/nested/item → open (no trailing show)
  // - /id/nested/item/show → DON'T open (nested structure ending with show)
  const resource = useResourceContext()
  const {name, options} = useResourceDefinition()
  const redirect = useRedirect();
  const translate = useTranslate()
  const closeToList = () => redirect("list", resource, dialogId)


const isCurrentResource = useMemo(() => {
    if (resource === undefined) return false
    const segments = location.pathname
        .replace(/^\/|\/$/g, '')
        .split('/');

    const resourceIndex = segments.lastIndexOf(resource);

    if (resourceIndex === -1) {
        return false;
    }

    // resource/:id must exist
    if (!segments[resourceIndex + 1]) {
        return false;
    }

    // Everything following resource/:id
    const trailingSegments = segments.slice(resourceIndex + 2);

    // "show" belongs to the current resource
    // but anything after "show" means we're inside a nested resource
    if (trailingSegments[0] === 'show') {
        return trailingSegments.length === 1;
    }

    return trailingSegments.length === 0;
}, [location.pathname, resource]);

  const title = useMemo(()=>(
    isCreate ? 
    <Fragment>{translate('ra.action.create')} {options.label ?? name}</Fragment>: 
    <Fragment>{translate('ra.action.edit')} <RecordRepresentation /></Fragment>
  ),[isCreate, options])

  const actions = useMemo(()=>(
   <Fragment>
    <SaveButton type='button' alwaysEnable/>
    {options.hasDelete && !isCreate ? <DeleteButton />: null}
   </Fragment>
  ),[isCreate, options])

  return (

    <ContextBasedDialog
      open={Boolean(open) ||
        (isCurrentResource && (Boolean(dialogId) || isCreate))}
      onClose={closeToList}
      title={<DialogHeader onClose={closeToList}>{title}</DialogHeader>}
      actions={actions}
      {...rest}
    >
      {children}
    </ContextBasedDialog>
  )
}

const DialogEditRoute = ({
    editGuesserProps,
}: {
    editGuesserProps?: EditGuesserProps;
}) => {
const { dialogId } = useParams<{ dialogId: string }>();
return (
  <EditGuesser
      id={dialogId}
      simpleFormProps={{
          component: DialogRoute,
          toolbar: false,
      }}
      {...editGuesserProps}
  />
);
};

export interface ListWithDialogsProps {
  listGuesserProps?: ListGuesserProps
  editGuesserProps?: EditGuesserProps
  createGuesserProps?: CreateGuesserProps
}

const ListWithDialogs = (
  {
    listGuesserProps,
    editGuesserProps,
    createGuesserProps
  }: ListWithDialogsProps
) => {
  const {hasEdit, hasCreate} = useResourceDefinition()
  return (
    <Fragment>

      <ListGuesser
        {...listGuesserProps}
      />
      <Routes>
        {
          hasEdit ?
          <Route
              path={`:dialogId/*`}
              element={
                <DialogEditRoute
                  editGuesserProps={editGuesserProps}
                />
              }
          />:
          null
        }
        {
          hasCreate ?
          <Route
            path={`create`}
            element={
            <CreateGuesser
              simpleFormProps={
                {
                  component: DialogRoute,
                  toolbar: false
                }
              }
              {...createGuesserProps}
            />}
          />:
          null
        }
      </Routes>
    </Fragment>
  )
}



export default ListWithDialogs;
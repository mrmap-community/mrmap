import CloseIcon from '@mui/icons-material/Close';
import { Dialog, DialogActions, DialogContent, DialogProps, DialogTitle, IconButton, Stack, Typography } from "@mui/material";
import { useMemo } from 'react';
import { DeleteButton, RecordRepresentation, SaveButton, useRedirect, useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import { Route, Routes, useParams } from 'react-router';
import { useLocation } from 'react-router-dom';
import { Fragment } from "react/jsx-runtime";
import CreateGuesser, { CreateGuesserProps } from './CreateGuesser';
import EditGuesser, { EditGuesserProps } from "./EditGuesser";
import ListGuesser, { ListGuesserProps } from "./ListGuesser";


const DialogRoute = (
  {
    children,
    open,
    ...rest
  }: DialogProps
) => {
  const location = useLocation()
  const { id } = useParams<{ id?: string }>();
  // detect "create" route reliably: check last path segment
  const lastSegment = location.pathname.replace(/\/$/, '').split('/').pop();
  const isCreate = id === 'create' || lastSegment === 'create';
  const resource = useResourceContext()
  const {name, options} = useResourceDefinition()
  const redirect = useRedirect();
  const translate = useTranslate()

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

    <Dialog 
      open={open || Boolean(id) || isCreate}
      onClose={() => redirect("list", resource, id)}
      scroll={'paper'}
      maxWidth={'xl'}
      fullWidth
      aria-labelledby="scroll-dialog-title"
      aria-describedby="scroll-dialog-description"
      {...rest}
    >
      <DialogTitle id="scroll-dialog-title">
        <Stack 
          direction="row"
          sx={{
            justifyContent: "space-between"
          }}
        >
          <Typography variant='h6'>
            {title}
          </Typography>
          <IconButton onClick={() => redirect("list", resource, id)}>
            <CloseIcon />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent 
        dividers={true} 
        id="scroll-dialog-description"
      >
        {children}
      </DialogContent>
      <DialogActions style={{ justifyContent: "space-between" }}>
        {actions}
      </DialogActions>
    </Dialog>
  )
}


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
            path=":id/*"
            element={<EditGuesser
              simpleFormProps={
                {
                  component: DialogRoute,
                  toolbar: false
                }
              }
              {...editGuesserProps}
            />}
          />:
          null
        }
        {
          hasCreate ?
          <Route
            path="create"
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
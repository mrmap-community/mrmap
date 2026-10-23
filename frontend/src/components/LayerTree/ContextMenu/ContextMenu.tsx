import { useState } from 'react';
import { RecordContextProvider, useTranslate } from 'react-admin';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/Delete';
import Menu from "@mui/material/Menu";
import MenuList from '@mui/material/MenuList';

import { Position } from '../../../ows-lib/OwsContext/enums';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import EditAuthenticationsDialog from '../../MapViewer/OwsContextGuiActions/EditAuthenticationsDialog';
import ActivateLayerItem from './ActivateLayerItem';
import { useContextMenuBase } from "./ContextMenuBase";
import ContextMenuItem from './ContextMenuItem';
import DimensionItem from './DimensionItem';
import ManageAuthenticationItem from './ManageAuthenticationItem';
import StyleLegendItem from './StyleLegendItem';
import ZoomToLayerItem from './ZoomToLayerItem';


const MenuItems = ({ onManage }: { onManage: (folder?: string) => void }) => {
  const translate = useTranslate()
  const { node, close } = useContextMenuBase()
  const { owsContext, moveFeature, removeFeature } = useOwsContextBase()

  if (node === undefined ) return null

  // the tree hands over a node of the revision it rendered with; the current context answers the edit
  const target = owsContext.findResourceByFolder(node.properties.folder)

  // the previous and the next sibling decide which moves exist, exactly like in drag and drop:
  // a move towards a boundary sibling is the same left/right move the sortable tree performs
  const siblings = target !== undefined ? owsContext.getSiblingsOf(target) : []
  const canMoveUp = siblings.some(sibling =>
    sibling.getFolderIndex() === (target?.getFolderIndex() ?? 0) - 1)
  const canMoveDown = siblings.some(sibling =>
    sibling.getFolderIndex() === (target?.getFolderIndex() ?? 0) + 1)

  const move = (direction: -1 | 1) => {
    if (target === undefined) return
    const boundary = siblings.find(sibling =>
      sibling.getFolderIndex() === target.getFolderIndex() + direction)
    if (boundary === undefined) return
    // move up swaps the layer with its previous sibling, move down with its next one; both are
    // the same "left of" move the drag and drop performs, which keeps sibling indices gap free
    const [source, before] = direction === -1 ? [target, boundary] : [boundary, target]
    moveFeature(source, before, Position.left)
    close()
  }

  // removing a group removes its whole subtree: the children would lose the grouping the
  // document describes for them; everything else in the context keeps its id, its activation
  // and its order
  const remove = () => {
    if (target?.properties.folder === undefined) return
    removeFeature(target.properties.folder)
    close()
  }

  const label = (key: string) => translate(`LayerTree.ContextMenu.${key}`)

  return (
    <MenuList
    >
      <ContextMenuItem
        onClick={() => move(-1)}
        disabled={!canMoveUp}
        icon={<ArrowUpwardIcon fontSize="small"/>}
        label={label('moveUp')}
      />
      <ContextMenuItem
        onClick={() => move(1)}
        disabled={!canMoveDown}
        icon={<ArrowDownwardIcon fontSize="small"/>}
        label={label('moveDown')}
      />
      <ContextMenuItem
        onClick={remove}
        icon={<DeleteIcon fontSize="small"/>}
        label={label('remove')}
      />
      <StyleLegendItem/>
      <DimensionItem/>
      <ManageAuthenticationItem onManage={onManage}/>
      <ZoomToLayerItem/>
      <ActivateLayerItem/>
    </MenuList>
  )
}


const ContextMenu = () => {
  const {isOpen, close, mouseX, mouseY, record} = useContextMenuBase()
  
  const [authenticationEditor, setAuthenticationEditor] = useState<{ folder?: string }>();

  // Only render Menu if we have valid coordinates
  if (!isOpen || mouseX === undefined || mouseY === undefined) {
    if (!authenticationEditor) return null
  }
  
  return (
    <RecordContextProvider
      value={record}
    >
      <EditAuthenticationsDialog open={Boolean(authenticationEditor)} folder={authenticationEditor?.folder} setOpen={open => { if (!open) setAuthenticationEditor(undefined); }} />
      <Menu
        open={isOpen}
        onClose={close}
        anchorReference="anchorPosition"
        anchorPosition={{ top: mouseY ?? 0, left: mouseX ?? 0 }}
        anchorOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
        transformOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
      >
        <MenuItems onManage={folder => { setAuthenticationEditor({ folder }); close(); }} />
      </Menu>
    </RecordContextProvider>
  )
}

export default ContextMenu
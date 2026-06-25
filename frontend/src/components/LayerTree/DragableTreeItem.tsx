import { useCallback, useEffect, useMemo, useRef, type ReactNode } from 'react';

import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import { TreeItemProps } from '@mui/lab';
import { TreeItem } from '@mui/x-tree-view';
import Sortable from 'sortablejs';
import { v4 as uuidv4 } from 'uuid';

import { Position } from '../../ows-lib/OwsContext/enums';
import { OWSResource } from '../../ows-lib/OwsContext/types';
import { getParentFolder } from '../../ows-lib/OwsContext/utils';
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';
import { useContextMenuBase } from './ContextMenuBase';


// TODO: typeof should be any other type
// to avoid icons for imaginary tree items
function ImaginaryIcon(props: React.PropsWithoutRef<typeof KeyboardArrowRightIcon>) {
  return <div />;
}
export interface DragableTreeItemProps extends TreeItemProps{
    node: OWSResource
    sortable?: Sortable.Options
    imaginary?: boolean
  }
  
export const DragableTreeItem = ({
    node,
    sortable,
    imaginary = false,
    ...props
  }: DragableTreeItemProps): ReactNode => {
    const ref = useRef(null)
    const { owsContext, moveFeature } = useOwsContextBase()
    const { setContextMenu } = useContextMenuBase()    
    const createSortable = useCallback(()=>{
      if (ref.current === null || ref.current === undefined) return
  
      Sortable.create(ref.current, {
        group: {name: 'general',},
        animation: 150,
        fallbackOnBody: true,
        swapThreshold: 0.25,
        
        onEnd: (event) => {
          const evt = {...event}
  
          // cancel the UI update so <framework> will take care of it
          event.item.remove();
          if (event.oldIndex !== undefined) {
            event.from.insertBefore(event.item, event.from.children[event.oldIndex]);
          }
  
          const targetFolder = evt.to.dataset.owscontextFolder
          if (targetFolder === undefined) return
          const target = owsContext.findResourceByFolder(targetFolder)

          // get the correct source object (not a shallow coppy)
          const sourceFolder = node.properties.folder

          if (sourceFolder === undefined) return
          const source = owsContext.findResourceByFolder(sourceFolder)
          if (source == undefined) return

          if (target === undefined) {
            // undefined signals new subtree move event
            // move the node as child to the fictive parent
            const parentFolder = getParentFolder(targetFolder)
            if (parentFolder === undefined) return
            const parent = owsContext.findResourceByFolder(parentFolder)
            if (parent === undefined) return
            moveFeature(source, parent, Position.firstChild)          
          } else {
            const newIndex = evt.newIndex
            if (newIndex === 0) {
              moveFeature(source, target, Position.left)
            } else if (newIndex === 1) {
              moveFeature(source, target, Position.right)
            }
          }
  
        },
        ...sortable
      })
  
    }, [owsContext, ref, moveFeature])
  
    useEffect(()=>{
      createSortable()
    },[])
    

    const isLeaf = useMemo(() => {
      if (node.properties.folder !== undefined) {
        const resource = owsContext.findResourceByFolder(node.properties.folder)
        if (resource !== undefined) {
          return owsContext.isLeafNode(resource)
        }
      }
      return false
    },[owsContext, node])

    const onContextMenu = useCallback((event: React.MouseEvent<HTMLLIElement>) => {
      event.preventDefault()
      event.stopPropagation()
      setContextMenu({
        node: node,
        itemId: node.properties.folder,
        isOpen: true,
        anchorElement: event.currentTarget,
        mouseX: event.clientX,
        mouseY: event.clientY
      })

    }, [node, setContextMenu])

    return (
      <TreeItem
        ref={ref}
        itemId={node.properties.folder ?? uuidv4()}
        slots={{
          expandIcon: !isLeaf ? KeyboardArrowRightIcon: ImaginaryIcon,
          collapseIcon: !isLeaf ? KeyboardArrowDownIcon: ImaginaryIcon
        }}
        {...props}
        data-owscontext-folder={imaginary ? `${node.properties.folder}/0`: node.properties.folder}
        onContextMenu={onContextMenu}
      >
        {/* imaginary child node to create new childs */}
        {!imaginary && isLeaf ? <DragableTreeItem node={node} imaginary={true}></DragableTreeItem>: null}
        {/* append all origin children too */}
        {props.children}
      </TreeItem>
    )
  
  }
  
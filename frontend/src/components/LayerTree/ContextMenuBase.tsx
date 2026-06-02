
import { TreeViewItemId } from "@mui/x-tree-view/models/items";
import { Dispatch, PropsWithChildren, ReactNode, SetStateAction, createContext, useContext, useMemo, useState } from "react";



export interface ContextMenuBaseProps {
  itemId: TreeViewItemId;
  isOpen: boolean;
  anchorElement: HTMLElement | null;
  mouseX?: number;
  mouseY?: number;
}

export interface ContextMenuBaseType extends ContextMenuBaseProps {
  setContextMenu: Dispatch<SetStateAction<ContextMenuBaseProps>>;
  close: () => void;
}

export const context = createContext<ContextMenuBaseType | undefined>(undefined)


export const ContextMenuBase = ({children}: PropsWithChildren): ReactNode => {
  const [itemId, setItemId] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [anchorElement, setAnchorElement] = useState<HTMLElement | null>(null)
  const [mouseX, setMouseX] = useState<number | undefined>()
  const [mouseY, setMouseY] = useState<number | undefined>()
  const value = useMemo<ContextMenuBaseType>(() => {
    return {
      itemId: itemId,
      isOpen: isOpen,
      anchorElement: anchorElement,
      mouseX: mouseX,
      mouseY: mouseY,
      setContextMenu: ({itemId, isOpen, anchorElement, mouseX, mouseY}: ContextMenuBaseProps) => {

        console.log("set context menu", {itemId, isOpen, anchorElement, mouseX, mouseY})
        setItemId(itemId)
        setIsOpen(isOpen)
        setAnchorElement(anchorElement)
        setMouseX(mouseX)
        setMouseY(mouseY)
      },
      close: () => {
        setIsOpen(false)
        setMouseX(undefined)
        setMouseY(undefined)
      }
    }
  }, [itemId, isOpen, anchorElement, mouseX, mouseY])
    

  return (
    <context.Provider
      value={value}
    >
      {children}
    </context.Provider>
  )

};

export const useContextMenuBase = (): ContextMenuBaseType => {
  const ctx = useContext(context)

  if (ctx === undefined) {
    throw new Error('useContextMenuBase must be inside a ContextMenuBase')
  }
  return ctx
};

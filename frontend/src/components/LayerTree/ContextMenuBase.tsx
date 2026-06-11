
import { Dispatch, PropsWithChildren, ReactNode, SetStateAction, createContext, useContext, useMemo, useState } from "react";
import { TreeifiedOWSResource } from "../../ows-lib/OwsContext/types";



export interface ContextMenuBaseProps {
  node: TreeifiedOWSResource;
  itemId?: string;
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
  const [node, setNode] = useState<TreeifiedOWSResource | undefined>(undefined)
  const [itemId, setItemId] = useState<string | undefined>(undefined)
  const [isOpen, setIsOpen] = useState(false)
  const [anchorElement, setAnchorElement] = useState<HTMLElement | null>(null)
  const [mouseX, setMouseX] = useState<number | undefined>()
  const [mouseY, setMouseY] = useState<number | undefined>()
  const value = useMemo<ContextMenuBaseType>(() => {
    return {
      node: node,
      itemId: itemId,
      isOpen: isOpen,
      anchorElement: anchorElement,
      mouseX: mouseX,
      mouseY: mouseY,
      setContextMenu: ({node, itemId, isOpen, anchorElement, mouseX, mouseY}: ContextMenuBaseProps) => {
        setNode(node)
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
  }, [node, isOpen, anchorElement, mouseX, mouseY])
    

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


import { PropsWithChildren, ReactNode, createContext, useCallback, useContext, useMemo, useState } from "react";
import { RaRecord } from "react-admin";

import { OWSResource } from "../../../ows-lib/OwsContext/core";



export interface ContextMenuBaseProps {
  node?: OWSResource;
  record?: RaRecord;
  itemId?: string;
  isOpen: boolean;
  anchorElement: HTMLElement | null;
  mouseX?: number;
  mouseY?: number;
}

export interface ContextMenuBaseType extends ContextMenuBaseProps {
  controlsId?: string | number;
  setControlsId: (id?: string | number) => void;
  pinnedId?: string | number;
  setPinnedId: (id?: string | number) => void;
  setContextMenu: (value: ContextMenuBaseProps) => void;
  close: () => void;
}

export const context = createContext<ContextMenuBaseType | undefined>(undefined)


export const ContextMenuBase = ({children, onOpenControls}: PropsWithChildren<{ onOpenControls?: () => void }>): ReactNode => {
  const [controlsId, updateControlsId] = useState<string | number>();
  const [pinnedId, setPinnedId] = useState<string | number>();
  const [node, setNode] = useState<OWSResource | undefined>(undefined)
  const [itemId, setItemId] = useState<string | undefined>(undefined)
  const [isOpen, setIsOpen] = useState(false)
  const [anchorElement, setAnchorElement] = useState<HTMLElement | null>(null)
  const [mouseX, setMouseX] = useState<number | undefined>()
  const [mouseY, setMouseY] = useState<number | undefined>()
  const [record, setRecord] = useState<RaRecord | undefined>()

  const setControlsId = useCallback((id?: string | number) => {
    updateControlsId(id);
    if (id !== undefined) onOpenControls?.();
  }, [onOpenControls]);

  const value = useMemo<ContextMenuBaseType>(() => {
    return {
      controlsId, setControlsId, pinnedId, setPinnedId,
      node: node,
      record: record,
      itemId: itemId,
      isOpen: isOpen,
      anchorElement: anchorElement,
      mouseX: mouseX,
      mouseY: mouseY,
      setContextMenu: ({node, record, itemId, isOpen, anchorElement, mouseX, mouseY}: ContextMenuBaseProps) => {
        setNode(node)
        setRecord(record)
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
  }, [node, isOpen, anchorElement, mouseX, mouseY, record, itemId, controlsId, pinnedId, setControlsId])
    

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

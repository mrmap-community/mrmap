import { PropsWithChildren, ReactNode, createContext, useContext, useMemo, useState } from "react";


export interface DialogContextBaseProps {
  isOpen: boolean;
  title: any;
  content: any;
  actions: any;
}

export interface DialogContextBaseType extends DialogContextBaseProps {
  open: (title: any, content:any, actions: any) => void;
  close: () => void;
}

export const context = createContext<DialogContextBaseType | undefined>(undefined)


export const DialogBase = ({children}: PropsWithChildren): ReactNode => {
  const [isOpen, setIsOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState()
  const [actions, setActions] = useState()
  const value = useMemo<DialogContextBaseType>(() => {
    return {
      isOpen: isOpen,
      title: title,
      content: content,
      actions: actions,
      open: (title, content, actions) => {
        setTitle(title)
        setContent(content)
        setActions(actions)
        setIsOpen(true)
      },
      close: () => {
        setIsOpen(false)
      }
    }
  }, [isOpen])
    

  return (
    <context.Provider
      value={value}
    >
      {children}
    </context.Provider>
  )

};

export const useDialogContextBase = (): DialogContextBaseType => {
  const ctx = useContext(context)

  if (ctx === undefined) {
    throw new Error('useDialogContextBase must be inside a DialogBase')
  }
  return ctx
};

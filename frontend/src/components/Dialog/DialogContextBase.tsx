import {
  PropsWithChildren,
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";

export interface DialogContextBaseProps {
  isOpen: boolean;
  title: ReactNode;
  content: ReactNode;
  actions: ReactNode;
}

export interface DialogContextBaseType extends DialogContextBaseProps {
  open: (title: ReactNode, content: ReactNode, actions: ReactNode) => void;
  close: () => void;
}

export const context = createContext<DialogContextBaseType | undefined>(
  undefined,
);

/**
 * Holds the title, content and actions of one dialog instance.
 *
 * The exposed value is rebuilt on every render, so `open` replaces title,
 * content and actions even while the dialog is already open and consumers
 * never read a stale draft.
 */
export const DialogBase = ({ children }: PropsWithChildren): ReactNode => {
  const [isOpen, setIsOpen] = useState(false);
  const [title, setTitle] = useState<ReactNode>();
  const [content, setContent] = useState<ReactNode>();
  const [actions, setActions] = useState<ReactNode>();
  const open = useCallback(
    (title: ReactNode, content: ReactNode, actions: ReactNode) => {
      setTitle(title);
      setContent(content);
      setActions(actions);
      setIsOpen(true);
    },
    [],
  );
  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  return (
    <context.Provider value={{ isOpen, title, content, actions, open, close }}>
      {children}
    </context.Provider>
  );
};

export const useDialogContextBase = (): DialogContextBaseType => {
  const ctx = useContext(context);

  if (ctx === undefined) {
    throw new Error("useDialogContextBase must be inside a DialogBase");
  }
  return ctx;
};

/** The context of the surrounding `DialogBase` or `undefined` outside one. */
export const useOptionalDialogContextBase = ():
  DialogContextBaseType | undefined => useContext(context);

import { useCallback } from "react";
import {
  useListContext,
  useNotify,
  useResourceContext,
  useTranslate,
} from "react-admin";
import { useDialogContextBase } from "./DialogContextBase";

const useDialogMutationSuccess = (
  action: "created" | "updated" | "deleted",
) => {
  const { refetch } = useListContext();
  const resource = useResourceContext();
  const notify = useNotify();
  const translate = useTranslate();
  const { close } = useDialogContextBase();
  return useCallback(() => {
    refetch();
    close();
    notify(`resources.${resource}.notifications.${action}`, {
      type: "success",
      messageArgs: {
        smart_count: 1,
        _: translate(`ra.notification.${action}`, { smart_count: 1 }),
      },
      undoable: false,
    });
  }, [action, resource, refetch, close, notify, translate]);
};

export default useDialogMutationSuccess;

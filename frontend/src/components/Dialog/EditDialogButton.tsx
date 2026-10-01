import DialogHeader from "./DialogHeader";
import useDialogMutationSuccess from "./useDialogMutationSuccess";
import EditIcon from "@mui/icons-material/Edit";
import { type ButtonOwnProps } from "@mui/material";
import { Fragment } from "react";
import {
  Button,
  DeleteButton,
  EditProps,
  RecordRepresentation,
  SaveButton,
  useRecordContext,
  useResourceDefinition,
  useTranslate,
} from "react-admin";
import EditGuesser, {
  EditGuesserProps,
} from "../../jsonapi/components/EditGuesser";
import { FieldDefinition } from "../../jsonapi/utils";
import ContextBasedDialog from "./Dialog";
import { DialogBase, useDialogContextBase } from "./DialogContextBase";

export interface EditDialogProps extends Partial<EditProps> {
  isOpen?: boolean;
  onClose?: () => void;
  updateFieldDefinitions?: FieldDefinition[];
}

export interface EditDialogButtonProps {
  buttonProps?: ButtonOwnProps;
  guesserProps?: EditGuesserProps;
}

const DefaultTitle = () => {
  const translate = useTranslate();

  return (
    <DialogHeader>
      {translate("ra.action.edit")} <RecordRepresentation />
    </DialogHeader>
  );
};

const DefaultActions = () => {
  const onEditSuccess = useDialogMutationSuccess("updated");
  const onDeleteSuccess = useDialogMutationSuccess("deleted");
  return (
    <Fragment>
      <SaveButton
        mutationOptions={{ onSuccess: onEditSuccess }}
        type="button"
        alwaysEnable
      />
      <DeleteButton
        redirect={false}
        mutationOptions={{ onSuccess: onDeleteSuccess }}
      />
    </Fragment>
  );
};

const EditDialogButtonCore = ({
  buttonProps,
  guesserProps,
}: EditDialogButtonProps) => {
  const record = useRecordContext();
  const { open } = useDialogContextBase();

  return (
    <Fragment>
      <Button
        label="Edit"
        onClick={() => open(<DefaultTitle />, null, <DefaultActions />)}
        {...buttonProps}
      >
        <EditIcon />
      </Button>
      <EditGuesser
        id={record?.id}
        redirect={false}
        sx={{
          // otherwise the EditGuesser div will create some spacing behind the edit button...
          display: "none !important",
        }}
        simpleFormProps={{
          component: ContextBasedDialog,
          children: null,
          toolbar: false,
        }}

        {...guesserProps}
      ></EditGuesser>
    </Fragment>
  );
};

const EditDialogButton = ({ ...rest }: EditDialogButtonProps) => {
  const record = useRecordContext();
  const { hasEdit } = useResourceDefinition();

  if (!hasEdit || record === undefined) {
    return null;
  }

  return (
    <DialogBase>
      <EditDialogButtonCore {...rest} />
    </DialogBase>
  );
};

export default EditDialogButton;

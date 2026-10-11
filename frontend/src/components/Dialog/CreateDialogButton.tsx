import DialogHeader from "./DialogHeader";
import useDialogMutationSuccess from "./useDialogMutationSuccess";
import AddIcon from "@mui/icons-material/Add";
import { type ButtonOwnProps } from "@mui/material";
import { Fragment } from "react";
import {
  Button,
  SaveButton,
  useResourceDefinition,
  useTranslate,
} from "react-admin";
import CreateGuesser, {
  CreateGuesserProps,
} from "../../jsonapi/components/CreateGuesser";
import ContextBasedDialog from "./Dialog";
import { DialogBase, useDialogContextBase } from "./DialogContextBase";

export interface CreateDialogButtonProps {
  buttonProps?: ButtonOwnProps;
  guesserProps?: CreateGuesserProps;
}

const DefaultTitle = () => {
  const translate = useTranslate();
  const { name } = useResourceDefinition();
  return (
    <DialogHeader>
      {translate("ra.action.create")} {name}
    </DialogHeader>
  );
};

const DefaultActions = () => {
  const onSuccess = useDialogMutationSuccess("created");
  return (
    <Fragment>
      <SaveButton
        mutationOptions={{ onSuccess: onSuccess }}
        type="button"
        alwaysEnable
      />
    </Fragment>
  );
};

const CreateDialogButtonCore = ({
  buttonProps,
  guesserProps,
}: CreateDialogButtonProps) => {
  const { open } = useDialogContextBase();
  return (
    <Fragment>
      <Button
        label="ra.action.create"
        onClick={() => open(<DefaultTitle />, null, <DefaultActions />)}
        {...buttonProps}
      >
        <AddIcon />
      </Button>
      <CreateGuesser
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
        referenceInputs={guesserProps?.referenceInputs}
        {...guesserProps}
      ></CreateGuesser>
    </Fragment>
  );
};

const CreateDialogButton = ({ ...rest }: CreateDialogButtonProps) => {
  const { hasCreate } = useResourceDefinition();

  if (!hasCreate) {
    return null;
  }

  return (
    <DialogBase>
      <CreateDialogButtonCore {...rest} />
    </DialogBase>
  );
};

export default CreateDialogButton;

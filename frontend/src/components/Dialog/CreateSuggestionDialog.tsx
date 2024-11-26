import { useCreateSuggestionContext } from "react-admin";
import CreateDialog, { CreateDialogProps } from "./CreateDialog";

const CreateSuggestionDialog = (
  props: CreateDialogProps
) => {

  const { onCancel, onCreate } = useCreateSuggestionContext();

  return (
    <CreateDialog
      onCancel={onCancel}
      onCreate={onCreate}
      {...props}
    />
  )
}

export default CreateSuggestionDialog
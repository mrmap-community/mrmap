import { useCreateSuggestionContext } from "react-admin";

import CreateDialogButton, { CreateDialogButtonProps } from "./CreateDialogButton";

const CreateSuggestionDialog = (
  props: CreateDialogButtonProps
) => {

  const { onCreate } = useCreateSuggestionContext();
  
  return (
    <CreateDialogButton
      guesserProps={{
        mutationOptions: {
          onSuccess: (data) => {
            onCreate(data);
          }
        }
        
      }}
      {...props}
    />
  )
}

export default CreateSuggestionDialog
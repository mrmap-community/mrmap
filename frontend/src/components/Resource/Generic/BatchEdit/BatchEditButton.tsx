import { useState } from "react";
import {
  Button,
  type Identifier,
  useListContext,
} from "react-admin";

import EditIcon from "@mui/icons-material/Edit";

import useOperation from "../../../../jsonapi/hooks/useOperation";
import BatchEditDialog from "./BatchEditDialog";

/**
 * The bulk action which opens the batch edit over the current selection (#1249).
 *
 * It offers itself only to resources the api answers a PATCH for; which of
 * the selected records may actually be written is decided per request by the
 * server's `allowedActions` - the selection is convenience, never authority.
 */
const BatchEditButton = () => {
  const { resource, selectedIds = [] } = useListContext();
  const hasPatch = useOperation(`partial_update_${resource}`) !== undefined;
  const [ids, setIds] = useState<Identifier[]>();

  if (!hasPatch) return null;
  return (
    <>
      <Button
        label="batchEdit.action"
        startIcon={<EditIcon />}
        onClick={() => setIds([...selectedIds])}
      />
      {ids !== undefined && (
        <BatchEditDialog
          resource={resource}
          ids={ids}
          onClose={() => setIds(undefined)}
        />
      )}
    </>
  );
};

export default BatchEditButton;

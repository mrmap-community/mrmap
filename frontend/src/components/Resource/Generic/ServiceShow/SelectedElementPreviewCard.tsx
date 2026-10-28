import { RecordContext, useTranslate } from "react-admin";

import { Typography } from "@mui/material";

import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import SimpleCard from "../../../MUI/SimpleCard";
import ElementLivePreview from "./ElementLivePreview";

/**
 * The preview of the layer or feature type a screen of elements has selected.
 *
 * The click of the list names the element, the card asks the service which owns it for the map of
 * that one element, the same way the inspection of an element of a service does: both hand the
 * element to the preview as its record context. Without a click there is nothing to ask, and the
 * card names the click which would answer it.
 */
const SelectedElementPreviewCard = () => {
  const { selectedRecord } = useSelectedRecordContext();
  const translate = useTranslate();

  return (
    <SimpleCard
      title={translate("layerInspection.preview")}
      cardProps={{ variant: "outlined", sx: { width: "100%", height: "auto" } }}
    >
      {selectedRecord === undefined ? (
        <Typography variant="body2" color="text.secondary">
          {translate("layerInspection.select")}
        </Typography>
      ) : (
        <RecordContext value={selectedRecord}>
          <ElementLivePreview height={300} />
        </RecordContext>
      )}
    </SimpleCard>
  );
};

export default SelectedElementPreviewCard;

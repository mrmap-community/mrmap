import { useRecordContext, useTranslate } from "react-admin";

import DownloadIcon from "@mui/icons-material/Download";
import { Alert, Button, Stack, Typography } from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";

/**
 * The XML document a harvest import stored beside the parsed record.
 *
 * The api answers the stored file as the url of its media file (the
 * `xml_backup_file` field of the records); a record which was created in the
 * registry itself or imported before the storage existed answers none, and the
 * card says so instead of hiding the fact.
 */
const RecordDocuments = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;
  const storedXml = record.xmlBackupFile;
  return (
    <SimpleCard title={translate("recordShow.documents")}>
      <Stack spacing={1}>
        <Typography variant="body2" color="text.secondary">
          {translate("recordShow.storedXmlHint")}
        </Typography>
        {typeof storedXml === "string" && storedXml !== "" ? (
          <Button
            component="a"
            href={storedXml}
            target="_blank"
            rel="noopener noreferrer"
            variant="outlined"
            startIcon={<DownloadIcon />}
            sx={{ alignSelf: "flex-start" }}
          >
            {translate("recordShow.storedXml")}
          </Button>
        ) : (
          <Alert severity="info">{translate("recordShow.noStoredXml")}</Alert>
        )}
      </Stack>
    </SimpleCard>
  );
};

export default RecordDocuments;

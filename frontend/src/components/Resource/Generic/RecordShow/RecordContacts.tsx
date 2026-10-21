import {
  useRecordContext,
  useResourceContext,
  useTranslate,
  type RaRecord,
} from "react-admin";

import { Grid, Link, Stack } from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";
import RecordFields, { IncludedRecordFields } from "./RecordFields";

const Contact = ({ record }: { record?: RaRecord }) => (
  <Stack spacing={1}>
    <IncludedRecordFields
      resource="MetadataContact"
      record={record}
      sources={[
        "name",
        "personName",
        "address",
        "city",
        "postalCode",
        "stateOrProvince",
        "country",
        "facsimile",
      ]}
    />
    {record?.email && (
      <Link href={`mailto:${record.email}`}>{record.email}</Link>
    )}
    {record?.phone && <Link href={`tel:${record.phone}`}>{record.phone}</Link>}
  </Stack>
);

const RecordContacts = () => {
  const record = useRecordContext();
  const resource = useResourceContext();
  const translate = useTranslate();
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleCard title={translate("recordShow.metadataContact")}>
          <Contact record={record?.metadataContact} />
        </SimpleCard>
      </Grid>
      {resource === "DatasetMetadataRecord" && (
        <Grid size={{ xs: 12, md: 6 }}>
          <SimpleCard title={translate("recordShow.datasetContact")}>
            <Contact record={record?.datasetContact} />
          </SimpleCard>
        </Grid>
      )}
      <Grid size={12}>
        <SimpleCard title={translate("recordShow.usage")}>
          <IncludedRecordFields
            resource="Licence"
            record={record?.licence}
            sources={[
              "name",
              "identifier",
              "isOpenData",
              "symbolUrl",
              "descriptionUrl",
            ]}
          />
          <RecordFields
            sources={[
              "accessConstraints",
              "fees",
              "useLimitation",
              "licenseSourceNote",
            ]}
          />
        </SimpleCard>
      </Grid>
    </Grid>
  );
};

export default RecordContacts;

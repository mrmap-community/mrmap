import { Grid } from "@mui/material";
import { useTranslate } from "react-admin";
import SimpleCard from "../../../MUI/SimpleCard";
import RecordFields from "./RecordFields";

const RecordOverview = () => {
  const translate = useTranslate();
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleCard title={translate("recordShow.identity")}>
          <RecordFields
            sources={[
              "title",
              "abstract",
              "resourceIdentifier",
              "fileIdentifier",
              "code",
              "codeSpace",
              "dateStamp",
              "updateFrequencyCode",
              "format",
              "languages",
              "charset",
            ]}
          />
        </SimpleCard>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleCard title={translate("recordShow.quality")}>
          <RecordFields
            sources={[
              "keywords",
              "categories",
              "origin",
              "originUrl",
              "isSearchable",
              "isBroken",
              "insufficientQuality",
              "inspireInteroperability",
              "inspireTopConsistence",
              "lineageStatement",
              "hits",
            ]}
          />
        </SimpleCard>
      </Grid>
    </Grid>
  );
};

export default RecordOverview;

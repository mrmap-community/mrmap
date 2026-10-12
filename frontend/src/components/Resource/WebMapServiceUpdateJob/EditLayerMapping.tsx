import { useMemo } from "react";
import { Box, Stack, Typography } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import {
  type RaRecord,
  SaveButton,
  Toolbar,
  useRecordContext,
  useTranslate,
} from "react-admin";
import EditGuesser, {
  type EditGuesserProps,
} from "../../../jsonapi/components/EditGuesser";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import {
  type ServiceUpdateConfig,
  wmsUpdateConfig,
} from "../Generic/Update/serviceUpdateConfig";
import { useQueryParam } from "../../utils";

const ReviewToolbar = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Toolbar sx={{ bgcolor: "transparent", px: 0, flexWrap: "wrap", gap: 1 }}>
      <SaveButton
        type="button"
        alwaysEnable
        label="updateReview.confirm"
        icon={<CheckIcon />}
        transform={(data: RaRecord) => ({ ...data, isConfirmed: true })}
      />
      <SaveButton
        type="button"
        alwaysEnable={!!record?.isConfirmed}
        label="updateReview.savePending"
        variant="outlined"
        icon={<SaveOutlinedIcon />}
        transform={(data: RaRecord) => ({ ...data, isConfirmed: false })}
      />
      <Typography variant="caption" color="text.secondary">
        {translate("updateReview.savedOnSubmit")}
      </Typography>
    </Toolbar>
  );
};

export const EditLayerMapping = ({
  mapping,
  config = wmsUpdateConfig,
  ...rest
}: EditGuesserProps & { mapping?: RaRecord; config?: ServiceUpdateConfig }) => {
  const [selectedLayer] = useQueryParam(config.selectedParam);
  const job = useRecordContext();
  const translate = useTranslate();
  const definitions = useFieldsForOperation({
    operationId: `partial_update_${config.mappingResource}`,
  });
  const selectedMapping =
    mapping ??
    job?.mappings?.find(
      (item: RaRecord) => String(item[config.newElement]?.id) === selectedLayer,
    );
  const overrides = useMemo(
    () =>
      definitions.map((definition) => ({
        ...definition,
        props: {
          ...definition.props,
          ...(["job", config.newElement, "isConfirmed"].includes(
            definition.props.source,
          )
            ? { hidden: true, sx: { display: "none" } }
            : {}),
          ...(definition.props.source === config.oldElement
            ? {
                label: `${config.hasTree ? "updateReview" : "wfsUpdateReview"}.mapExisting`,
                helperText: `${config.hasTree ? "updateReview" : "wfsUpdateReview"}.mapHelp`,
                relatedResource: {
                  resource: config.serviceResource,
                  id: job?.service?.id,
                },
                initialFilter: { hasReverseMapping: false },
                fullWidth: true,
              }
            : {}),
        },
      })),
    [definitions, job?.service?.id, config],
  );
  if (!selectedMapping) return null;
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        {translate("updateReview.resolve")}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {translate(
          `${config.hasTree ? "updateReview" : "wfsUpdateReview"}.resolveHelp`,
        )}
      </Typography>
      <EditGuesser
        key={selectedMapping.id}
        resource={config.mappingResource}
        id={selectedMapping.id}
        redirect={false}
        title={false}
        actions={false}
        component={Box}
        updateFieldDefinitions={overrides}
        simpleFormProps={{ toolbar: <ReviewToolbar />, sx: { p: 0 } }}
        {...rest}
      />
    </Stack>
  );
};

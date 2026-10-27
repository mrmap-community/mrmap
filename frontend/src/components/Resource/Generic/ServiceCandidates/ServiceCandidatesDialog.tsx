import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ShowButton,
  useRecordContext,
  useResourceContext,
  useTranslate,
} from "react-admin";

import CheckIcon from "@mui/icons-material/Check";
import LoginIcon from "@mui/icons-material/Login";
import SearchIcon from "@mui/icons-material/Search";
import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Divider,
  List,
  ListItem,
  ListItemButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";

import ContextBasedDialog from "../../../Dialog/Dialog";
import DialogHeader from "../../../Dialog/DialogHeader";
import { useOpenCandidateInViewer } from "./useOpenCandidateInViewer";
import {
  useServiceCandidates,
  useValidateServiceCandidate,
  type CandidateState,
  type CandidateValidation,
  type RegisteredTarget,
  type ServiceCandidate,
} from "./useServiceCandidates";

export interface ServiceCandidatesDialogProps {
  open: boolean;
  onClose: () => void;
  /** Metadata resource to resolve; the surrounding one by default. */
  resource?: string;
  /** Record to resolve; the record of the surrounding context by default. */
  recordId?: string;
}

/** How loud the answer of a candidate is told to the user. */
const stateColor: Record<
  CandidateState,
  "success" | "warning" | "error" | "default"
> = {
  resolved: "success",
  ambiguous: "warning",
  unsupported: "warning",
  unavailable: "error",
  unvalidated: "default",
};

/** The json:api resource a registered target of the answer belongs to. */
const registeredResource: Record<RegisteredTarget["resource_type"], string> =
  {
    wms: "WebMapService",
    wfs: "WebFeatureService",
    csw: "CatalogueService",
  };

/** The host and path of an endpoint, so a row reads as an address. */
const endpointOf = (url: string) => {
  try {
    const endpoint = new URL(url);
    return `${endpoint.host}${endpoint.pathname}`;
  } catch {
    return url;
  }
};

/** The layer and feature type hints of the record and what they became. */
const CandidateHints = ({
  candidate,
  validation,
}: {
  candidate: ServiceCandidate;
  validation?: CandidateValidation;
}) => {
  const translate = useTranslate();
  const hints = [...(candidate.type_names ?? []), ...(candidate.layers ?? [])];
  const matched = validation?.matched_names ?? [];
  const unresolved = validation?.unresolved_hints ?? [];
  if (!hints.length && !unresolved.length) return null;
  // Until the endpoint was asked, every hint is only a hint of the record.
  const confirmed = matched.filter((name) => hints.includes(name));
  const unconfirmed = hints.filter((name) => !confirmed.includes(name));
  return (
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.5 }}>
      {confirmed.map((name) => (
        <Tooltip key={name} title={translate("serviceCandidates.confirmed")}>
          <Chip size="small" color="success" label={name} />
        </Tooltip>
      ))}
      {unconfirmed.map((name) => (
        <Chip
          key={name}
          size="small"
          variant="outlined"
          label={name}
          color={
            unresolved.includes(name) || validation ? "warning" : "default"
          }
        />
      ))}
      {unresolved
        .filter((name) => !hints.includes(name))
        .map((name) => (
          <Chip key={name} size="small" color="warning" label={name} />
        ))}
    </Stack>
  );
};

const CandidateRow = ({
  candidate,
  selected,
  onSelect,
  onCheck,
  validation,
  isChecking,
}: {
  candidate: ServiceCandidate;
  selected: boolean;
  onSelect: (url: string) => void;
  onCheck: (url: string) => void;
  validation?: CandidateValidation;
  isChecking: boolean;
}) => {
  const translate = useTranslate();
  const t = (key: string) => translate(`serviceCandidates.${key}`);
  const evidence = candidate.evidence ?? [];
  return (
    <ListItem disablePadding>
      <ListItemButton
        selected={selected}
        onClick={() => onSelect(candidate.url)}
        sx={{ alignItems: "flex-start", gap: 1 }}
      >
        <Stack spacing={0.5} sx={{ minWidth: 0, flex: 1 }}>
          <Stack direction="row" useFlexGap sx={{ alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {candidate.service || t("unknownService")}
            </Typography>
            {candidate.advertised_version && (
              <Chip
                size="small"
                variant="outlined"
                label={candidate.advertised_version}
              />
            )}
            {candidate.preferred && (
              <Chip size="small" color="primary" label={t("preferred")} />
            )}
            {candidate.derived && (
              <Tooltip title={t("derivedHint")}>
                <Chip size="small" variant="outlined" label={t("derived")} />
              </Tooltip>
            )}
            {/* protocol and origin, so several candidates read apart */}
            <Chip
              size="small"
              variant="outlined"
              label={t(`source.${candidate.source}`)}
            />
            {/* the answer of the endpoint replaces the promise of discovery */}
            <Chip
              size="small"
              color={stateColor[validation?.state ?? candidate.state]}
              icon={validation?.state === "resolved" ? <CheckIcon /> : undefined}
              label={t(`state.${validation?.state ?? candidate.state}`)}
            />
          </Stack>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ overflowWrap: "anywhere" }}
          >
            {endpointOf(candidate.url)}
          </Typography>
          <CandidateHints candidate={candidate} validation={validation} />
          {validation?.detail && validation.state !== "resolved" && (
            <Typography variant="caption" color="text.secondary">
              {validation.detail}
            </Typography>
          )}
          {evidence.length > 0 && (
            <Tooltip title={evidence.join("\n")}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  display: "-webkit-box",
                  WebkitLineClamp: 1,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {evidence[0]}
              </Typography>
            </Tooltip>
          )}
        </Stack>
        {/* every candidate may be asked, not only the ones which carry hints */}
        {!validation && (
          <Button
            size="small"
            startIcon={isChecking ? undefined : <SearchIcon />}
            disabled={isChecking}
            onClick={(event) => {
              // the row selects the candidate, the button asks its endpoint
              event.stopPropagation();
              onCheck(candidate.url);
            }}
          >
            {isChecking ? t("checking") : t("check")}
          </Button>
        )}
      </ListItemButton>
    </ListItem>
  );
};

/**
 * Which services can deliver what the record describes.
 *
 * The candidates come from the record itself: its own advertised endpoints, the
 * services whose harvested records name this dataset and — kept apart — the
 * resources which are registered already. Choosing a candidate adds it to the
 * current map without registering anything, so this dialog neither writes to the
 * registry nor replaces the layers the user has on the map.
 */
export const ServiceCandidatesDialog = ({
  open,
  onClose,
  resource: resourceProp,
  recordId,
}: ServiceCandidatesDialogProps): ReactNode => {
  const resourceFromContext = useResourceContext();
  const record = useRecordContext();
  const translate = useTranslate();
  const t = (key: string) => translate(`serviceCandidates.${key}`);
  const openInViewer = useOpenCandidateInViewer();
  const resource = resourceProp ?? resourceFromContext;
  const id = recordId ?? (record?.id === undefined ? undefined : String(record.id));
  const [selected, setSelected] = useState<string>();
  const [checked, setChecked] = useState<string>();
  /** Every endpoint which was asked keeps its answer, so comparing two
   *  candidates does not throw the first answer away. */
  const [answers, setAnswers] = useState<Record<string, CandidateValidation>>(
    {},
  );

  const resolution = useServiceCandidates(resource, id, open);
  const validation = useValidateServiceCandidate(resource, id, checked, open);
  useEffect(() => {
    if (checked === undefined || validation.data === undefined) return;
    const url = checked;
    const asked = validation.data;
    setAnswers((previous) =>
      previous[url] === asked ? previous : { ...previous, [url]: asked },
    );
  }, [checked, validation.data]);

  const dismiss = () => {
    setSelected(undefined);
    setChecked(undefined);
    setAnswers({});
    onClose();
  };
  const select = (url: string) => setSelected(url);
  const check = (url: string) => {
    setSelected(url);
    setChecked(url);
  };
  const addToMap = () => {
    if (selected === undefined) return;
    openInViewer(selected);
    dismiss();
  };

  const answer = resolution.data;
  const candidates = useMemo(() => answer?.candidates ?? [], [answer]);
  const registered = answer?.registered_targets ?? [];
  const hasCandidates = candidates.length > 0;

  return (
    <ContextBasedDialog
      open={open}
      onClose={dismiss}
      maxWidth="md"
      fullWidth
      contentDividers={false}
      title={
        <DialogHeader onClose={dismiss}>{t("title")}</DialogHeader>
      }
      description={t("description")}
      actions={
        <Stack direction="row" spacing={1}>
          <Button onClick={dismiss}>{translate("ra.action.cancel")}</Button>
          <Button
            color="primary"
            variant="contained"
            startIcon={<LoginIcon />}
            disabled={selected === undefined || resolution.isPending}
            onClick={addToMap}
          >
            {t("openInMap")}
          </Button>
        </Stack>
      }
    >
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        {resolution.isPending && (
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center" }}
          >
            <CircularProgress size={18} />
            <Typography variant="body2">{t("loading")}</Typography>
          </Stack>
        )}
        {resolution.error && (
          <Alert severity="error">
            {t(`error.${resolution.error.code}`)}
          </Alert>
        )}
        {!resolution.isPending &&
          !resolution.error &&
          answer?.status &&
          answer.status !== "ok" && (
            <Alert severity="info">{t(`status.${answer.status}`)}</Alert>
          )}
        {answer?.truncated && (
          <Alert severity="info">{t("truncated")}</Alert>
        )}
        {hasCandidates && (
          <List disablePadding>
            {candidates.map((candidate) => (
              <CandidateRow
                key={candidate.url}
                candidate={candidate}
                selected={selected === candidate.url}
                onSelect={select}
                onCheck={check}
                validation={answers[candidate.url]}
                isChecking={
                  checked === candidate.url && validation.isPending
                }
              />
            ))}
          </List>
        )}
        {/* a record which stores nothing is told apart from one which simply
            advertises no service */}
        {!resolution.isPending &&
          !resolution.error &&
          answer?.status === "ok" &&
          !hasCandidates && (
            <Typography>
              {registered.length
                ? t("candidatesNoneRegistered")
                : t("none")}
            </Typography>
          )}
        {answer?.warnings && answer.warnings.length > 0 && (
          <Stack spacing={0.5}>
            {answer.warnings.map((warning) => (
              <Typography key={warning} variant="caption" color="text.secondary">
                {warning}
              </Typography>
            ))}
          </Stack>
        )}
        {registered.length > 0 && (
          <Stack spacing={1}>
            <Divider />
            <Typography variant="subtitle2">
              {t("registeredTitle")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t("registeredHint")}
            </Typography>
            <List disablePadding>
              {registered.map((target) => (
                <ListItem key={`${target.resource_type}-${target.id}`}>
                  <Typography
                    variant="body2"
                    sx={{ minWidth: 0, flex: 1, overflowWrap: "anywhere" }}
                  >
                    {target.name}
                  </Typography>
                  <ShowButton
                    resource={registeredResource[target.resource_type]}
                    record={{ id: target.id, name: target.name }}
                    label="ra.action.show"
                    size="small"
                  />
                </ListItem>
              ))}
            </List>
          </Stack>
        )}
        {(answer?.non_service_links?.length ?? 0) > 0 && (
          <Typography variant="caption" color="text.secondary">
            {t("nonService")}
          </Typography>
        )}
      </Stack>
    </ContextBasedDialog>
  );
};

export default ServiceCandidatesDialog;

import type {
  CandidateValidation,
  ServiceCandidate,
} from "./useServiceCandidates";

import { useTranslate } from "react-admin";

import { Chip, Stack, Tooltip } from "@mui/material";

/**
 * The layer and feature type hints of the record and what they became.
 *
 * The candidate's row and the registration step show the same reading: what the
 * record hints, what the asked endpoint confirmed and what it left open. Until
 * an endpoint was asked, every hint is only a hint of the record.
 */
export const CandidateHints = ({
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

export default CandidateHints;

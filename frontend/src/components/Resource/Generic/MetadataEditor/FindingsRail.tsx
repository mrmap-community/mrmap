/**
 * The right rail of the record editor: the findings (#1245).
 *
 * It survives navigation because it is never a dialog: client pre-validation
 * of the profile rules keeps answering while the curator edits, and the
 * json:api errors of a refused save take over with the server's verdict —
 * each one jumpable through its `source.pointer`. The rail groups nothing
 * beyond errors before warnings; what GeoNetwork surfaces as raw XSLT text
 * never reaches here, only the message the rule itself states (#1243).
 */

import type { Finding } from "./types";

import { type ReactNode, type ReactElement } from "react";
import { useTranslate } from "react-admin";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import WarningIcon from "@mui/icons-material/Warning";
import {
  Box,
  Chip,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";

interface FindingsRailProps {
  findings: Finding[];
  /** camelCase source -> x-iso-path, for the caption under a finding */
  isoPaths: Record<string, string>;
  /** jump to the field the finding names (section switch + focus) */
  onJump?: (finding: Finding) => void;
  /** the provenance card under the findings: reuse of the show cards */
  sourceCard?: ReactNode;
  sx?: object;
}

const SeverityIcon = ({ finding }: { finding: Finding }) =>
  finding.severity === "error" ? (
    <ErrorIcon color="error" fontSize="small" />
  ) : (
    <WarningIcon color="warning" fontSize="small" />
  );

const FindingsRail = ({
  findings,
  isoPaths,
  onJump,
  sourceCard,
  sx,
}: FindingsRailProps): ReactElement => {
  const translate = useTranslate();
  const errors = findings.filter((f) => f.severity === "error").length;
  const warnings = findings.length - errors;
  return (
    <Stack spacing={2} sx={{ width: 320, flexShrink: 0, ...sx }}>
      <SimpleCard
        title={
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="h6">
              {translate("metadataEditor.validation")}
            </Typography>
            {errors > 0 && (
              <Chip
                size="small"
                color="error"
                label={translate("metadataEditor.errorCount", {
                  smart_count: errors,
                })}
              />
            )}
            {warnings > 0 && (
              <Chip
                size="small"
                color="warning"
                label={translate("metadataEditor.warningCount", {
                  smart_count: warnings,
                })}
              />
            )}
          </Stack>
        }
      >
        {findings.length === 0 ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <CheckCircleIcon color="success" fontSize="small" />
            <Typography variant="body2">
              {translate("metadataEditor.validationClean")}
            </Typography>
          </Stack>
        ) : (
          <Stack
            component="ul"
            spacing={1.5}
            sx={{ listStyle: "none", m: 0, p: 0 }}
          >
            {findings.map((finding) => (
              <Box
                key={finding.key}
                component="li"
                sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}
              >
                <SeverityIcon finding={finding} />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2">{finding.detail}</Typography>
                  {finding.field && isoPaths[finding.field] && (
                    <Typography
                      variant="caption"
                      component="code"
                      sx={{ display: "block", fontFamily: "monospace" }}
                    >
                      {isoPaths[finding.field]}
                    </Typography>
                  )}
                </Box>
                {finding.field && onJump && (
                  <IconButton
                    size="small"
                    aria-label={translate("metadataEditor.jumpToField", {
                      field: finding.field,
                    })}
                    onClick={() => onJump(finding)}
                  >
                    <OpenInNewIcon fontSize="small" />
                  </IconButton>
                )}
              </Box>
            ))}
          </Stack>
        )}
      </SimpleCard>
      {sourceCard}
    </Stack>
  );
};

export default FindingsRail;

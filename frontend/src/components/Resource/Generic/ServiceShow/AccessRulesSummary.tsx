import { useMemo, useState, type MouseEvent } from "react";
import { Link, Loading, type RaRecord, useBasename, useListContext, useTranslate } from "react-admin";

import {
  Alert,
  Button,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import FeatureGroupEditor from "../../../Input/FeatureGroupEditor";
import GeoJsonMap from "../../../MapContainer/GeoJsonMap";

interface AccessRulesConfig {
  contentSource: string;
  contentLabelKey: "layers" | "featureTypes";
}

// Presentation fields for the related rule list of each spatial service type.
const RULE_CONFIG: Record<string, AccessRulesConfig> = {
  AllowedWebMapServiceOperation: {
    contentSource: "securedLayers",
    contentLabelKey: "layers",
  },
  AllowedWebFeatureServiceOperation: {
    contentSource: "securedFeatureTypes",
    contentLabelKey: "featureTypes",
  },
};

const relatedRecords = (value: unknown): RaRecord[] =>
  Array.isArray(value) ? (value as RaRecord[]) : [];

// the api includes the related resources, so the readable representation
// arrives with the rule; an id-only linkage stays visible as an id
const displayName = (item: RaRecord): string =>
  (item.stringRepresentation as string) ??
  (item.name as string) ??
  (item.title as string) ??
  `#${String(item.id)}`;

const NameChips = ({ items, limit }: { items: RaRecord[]; limit?: number }) => {
  const translate = useTranslate();
  const [expanded, setExpanded] = useState(false);
  const hasMore = limit !== undefined && items.length > limit;
  const visibleItems = hasMore && !expanded ? items.slice(0, limit) : items;

  return (
    <Stack spacing={0.5} sx={{ minWidth: 0, alignItems: "flex-start" }}>
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ flexWrap: "wrap", rowGap: 0.5, maxWidth: "100%", maxHeight: 200, overflowY: "auto" }}
      >
        {visibleItems.map((item) => (
          <Chip
            key={String(item.id)}
            size="small"
            variant="outlined"
            label={displayName(item)}
            title={displayName(item)}
            sx={{ maxWidth: "100%" }}
          />
        ))}
      </Stack>
      {hasMore && (
        <Button
          size="small"
          aria-expanded={expanded}
          onClick={(event: MouseEvent) => {
            event.stopPropagation();
            setExpanded((value) => !value);
          }}
        >
          {expanded
            ? translate("accessRules.showLess")
            : translate("accessRules.showMore", { count: items.length - limit })}
        </Button>
      )}
    </Stack>
  );
};

interface AccessRulesSummaryProps {
  ruleResource: "AllowedWebMapServiceOperation" | "AllowedWebFeatureServiceOperation";
  serviceId?: RaRecord["id"];
}

/**
 * Summary of the current page of the related access rule list: which
 * groups are allowed to use which operations on which content, and where an
 * allowed area restricts the response spatially. It describes configured
 * rules only; the proxy decides effective access at request time.
 */
const AccessRulesSummary = ({ ruleResource, serviceId }: AccessRulesSummaryProps) => {
  const translate = useTranslate();
  const basename = useBasename();
  const config = RULE_CONFIG[ruleResource];
  const message = (key: string, options?: Record<string, unknown>) =>
    translate(`accessRules.${key}`, options);
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);

  const { data: records = [], isPending, error, refetch } = useListContext();

  const selected = useMemo(
    () => records.find((rule) => String(rule.id) === selectedId) ?? records[0],
    [records, selectedId],
  );
  const selectedArea = selected?.allowedArea as Record<string, unknown> | null | undefined;
  const selectedAreas = useMemo(
    () => ({
      type: "FeatureCollection",
      features: selectedArea
        ? [{ type: "Feature", properties: {}, geometry: selectedArea }]
        : [],
    }) as never,
    [selectedArea],
  );

  if (error)
    return (
      <Alert
        severity="error"
        action={
          <Button onClick={() => void refetch()}>
            {translate("ra.action.retry")}
          </Button>
        }
      >
        {message("loadError")}
      </Alert>
    );
  if (isPending) return <Loading />;
  if (records.length === 0)
    return (
      <Stack spacing={1}>
        <Typography variant="subtitle1">{message("title")}</Typography>
        <Typography variant="body2" color="text.secondary">
          {message("empty")}
        </Typography>
      </Stack>
    );

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle1">{message("title")}</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{message("operations")}</TableCell>
            <TableCell>{message("groups")}</TableCell>
            <TableCell>{message(config.contentLabelKey)}</TableCell>
            <TableCell>{message("area")}</TableCell>
            <TableCell align="right">{message("edit")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {records.map((rule) => {
            const id = String(rule.id);
            const isSelected = selected !== undefined && String(selected.id) === id;
            return (
              <TableRow
                key={id}
                hover
                selected={isSelected}
                onClick={() => setSelectedId(id)}
              >
                <TableCell>
                  <NameChips items={relatedRecords(rule.operations)} />
                </TableCell>
                <TableCell>
                  {relatedRecords(rule.allowedGroups).length === 0 ? (
                    // backend semantics: a rule without groups applies to every group
                    <Chip size="small" color="info" label={message("allGroups")} />
                  ) : (
                    <NameChips items={relatedRecords(rule.allowedGroups)} />
                  )}
                </TableCell>
                <TableCell sx={{ width: "50%", maxWidth: 360 }}>
                  <NameChips
                    key={`${ruleResource}-${id}`}
                    items={relatedRecords(rule[config.contentSource])}
                    limit={3}
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={rule.allowedArea == null ? "default" : "warning"}
                    label={
                      rule.allowedArea == null
                        ? message("unrestricted")
                        : message("restricted")
                    }
                  />
                </TableCell>
                <TableCell align="right">
                  {/* navigation to the authorized rule editor; react-admin
                      renders the permission state of that screen */}
                  <Button
                    size="small"
                    component={Link}
                    to={`${basename}/${ruleResource}/${id}/edit`}
                    onClick={(event: MouseEvent) => event.stopPropagation()}
                  >
                    {message("edit")}
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {selectedArea ? (
        <Stack spacing={1}>
          <Typography variant="body2">
            {message("mapScope", { rule: `#${String(selected?.id)}` })}
          </Typography>
          <GeoJsonMap id={`access-rules-${ruleResource}-${String(serviceId)}`}>
            <FeatureGroupEditor geoJson={selectedAreas} editable={false} />
          </GeoJsonMap>
        </Stack>
      ) : (
        // an empty allowed area means unrestricted access in the backend
        <Alert severity="info">
          {message("unrestrictedExplanation", { rule: `#${String(selected?.id)}` })}
        </Alert>
      )}
      <Typography variant="caption" color="text.secondary">
        {message("configuredOnly")}
      </Typography>
    </Stack>
  );
};

export default AccessRulesSummary;

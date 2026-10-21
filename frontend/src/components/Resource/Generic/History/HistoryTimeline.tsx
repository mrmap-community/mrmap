import { useId, useRef, useState } from "react";
import { useTranslate, type RaRecord } from "react-admin";

import CheckIcon from "@mui/icons-material/Check";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import DeleteIcon from "@mui/icons-material/Delete";
import UpdateIcon from "@mui/icons-material/Update";
import {
  alpha,
  Box,
  ButtonBase,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";

import HistoryEventDetails from "./HistoryEventDetails";

export interface HistoryRecord extends RaRecord {
  historyType: "created" | "updated" | "deleted";
  historyDate: string;
  actionLabel?: string;
  historyRelation?: { id: string | number } | null;
  historyUser?: { username: string } | null;
  delta?: { field: string; old?: unknown; new?: unknown }[] | null;
}

export interface TimelineRecord extends HistoryRecord {
  _type: string;
}

const eventKey = (event: TimelineRecord) => `${event._type}:${event.id}`;
const eventStyles = {
  created: { color: "success", label: "Created", Icon: CheckIcon },
  updated: { color: "info", label: "Updated", Icon: UpdateIcon },
  deleted: { color: "error", label: "Deleted", Icon: DeleteIcon },
} as const;

/** A single detail panel shared by a horizontally scrolling, newest-first timeline. */
const HistoryTimeline = ({ events }: { events: TimelineRecord[] }) => {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventButtons = useRef(new Map<string, HTMLButtonElement>());
  const detailsId = useId();
  const translate = useTranslate();
  const selected = events.find((event) => eventKey(event) === selectedKey);
  const scroll = (direction: number) => {
    const container = scrollRef.current;
    if (container)
      container.scrollBy({
        left: direction * container.clientWidth * 0.8,
        behavior: "smooth",
      });
  };
  const closeDetails = () => {
    if (selectedKey)
      eventButtons.current.get(selectedKey)?.focus({ preventScroll: true });
    setSelectedKey(null);
  };

  if (events.length === 0)
    return (
      <Typography color="text.secondary" sx={{ p: 2 }}>
        No changes to display.
      </Typography>
    );

  return (
    <>
      <Box
        ref={scrollRef}
        role="region"
        aria-label="History timeline, newest first"
        tabIndex={0}
        sx={{
          overflowX: "auto",
          overscrollBehaviorX: "contain",
          maxWidth: "100%",
          px: 2,
          py: 1.5,
          "&:focus-visible": {
            outline: "2px solid",
            outlineColor: "primary.main",
            outlineOffset: -2,
          },
        }}
      >
        <Box
          component="ol"
          sx={{
            display: "flex",
            listStyle: "none",
            m: 0,
            p: 0,
            width: "max-content",
            minWidth: "100%",
          }}
        >
          {events.map((event, index) => {
            const key = eventKey(event);
            const active = key === selectedKey;
            const { color, label: defaultLabel, Icon } = eventStyles[event.historyType];
            const label = event.actionLabel ?? defaultLabel;
            const date = new Date(event.historyDate);
            const relation = String(event.historyRelation?.id ?? "—");
            return (
              <Box
                component="li"
                key={key}
                sx={{
                  flex: "1 0 190px",
                  position: "relative",
                  "&::before": {
                    content: '""',
                    position: "absolute",
                    top: 45,
                    height: 2,
                    bgcolor: "divider",
                    left: index === 0 ? "50%" : 0,
                    right: index === events.length - 1 ? "50%" : 0,
                  },
                }}
              >
                <ButtonBase
                  ref={(node) => {
                    if (node) eventButtons.current.set(key, node);
                    else eventButtons.current.delete(key);
                  }}
                  aria-label={`${event._type} ${relation}, ${label}, ${date.toLocaleString()}`}
                  aria-expanded={active}
                  aria-controls={active ? detailsId : undefined}
                  onClick={() => setSelectedKey(active ? null : key)}
                  sx={{
                    width: "100%",
                    display: "flex",
                    flexDirection: "column",
                    gap: 0.75,
                    p: 1,
                    borderRadius: 1,
                    border: 1,
                    borderColor: active ? "primary.main" : "transparent",
                    bgcolor: (theme) =>
                      active
                        ? alpha(theme.palette.primary.main, 0.08)
                        : "transparent",
                    "&:hover": { bgcolor: "action.hover" },
                    "&.Mui-focusVisible": {
                      outline: "2px solid",
                      outlineColor: "primary.main",
                      outlineOffset: -2,
                    },
                  }}
                >
                  <Typography
                    variant="caption"
                    color={active ? "primary" : "text.secondary"}
                  >
                    {date.toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </Typography>
                  <Box
                    sx={{
                      width: 30,
                      height: 30,
                      display: "grid",
                      placeItems: "center",
                      borderRadius: "50%",
                      border: 1,
                      borderColor: `${color}.main`,
                      color: `${color}.main`,
                      bgcolor: "background.paper",
                      zIndex: 1,
                      boxShadow: (theme) =>
                        active
                          ? `0 0 0 4px ${alpha(theme.palette.primary.main, 0.15)}`
                          : "none",
                    }}
                  >
                    <Icon fontSize="small" />
                  </Box>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: active ? 600 : 400 }}
                  >
                    {event._type === "Layer" ? "Layer" : event._type === "FeatureType" ? "Feature type" : event._type === "HarvestedMetadataRelation" ? "Harvested record" : "Service"} · {label}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontFamily: "monospace", whiteSpace: "nowrap" }}
                  >
                    {relation.slice(0, 8)} · {date.toLocaleTimeString()}
                  </Typography>
                </ButtonBase>
              </Box>
            );
          })}
        </Box>
      </Box>
      <Stack
        direction="row"
        sx={{
          px: 2,
          pb: 1,
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Newest first · Select an event to show or hide details.
        </Typography>
        <Stack direction="row">
          <IconButton
            size="small"
            aria-label="Scroll to newer changes"
            onClick={() => scroll(-1)}
          >
            <ChevronLeftIcon />
          </IconButton>
          <IconButton
            size="small"
            aria-label="Scroll to older changes"
            onClick={() => scroll(1)}
          >
            <ChevronRightIcon />
          </IconButton>
        </Stack>
      </Stack>
      {selected && (
        <Box sx={{ borderTop: 1, borderColor: "divider", p: 2 }}>
          <Stack
            direction="row"
            sx={{
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 1,
            }}
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <HistoryEventDetails event={selected} id={detailsId} />
            </Box>
            <IconButton
              size="small"
              aria-label={translate("historyList.closeDetails", {
                _: "Close event details",
              })}
              onClick={closeDetails}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Box>
      )}
    </>
  );
};

export default HistoryTimeline;

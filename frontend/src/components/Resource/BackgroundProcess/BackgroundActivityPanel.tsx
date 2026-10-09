import { useId, useState } from "react";
import {
  Link,
  useCreatePath,
  useListContext,
  useTranslate,
} from "react-admin";
import { ReadyState } from "react-use-websocket";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import CloseIcon from "@mui/icons-material/Close";
import {
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  LinearProgress,
  Popover,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import RealtimeListBase from "../../../jsonapi/components/Realtime/RealtimeListBase";
import { useHttpClientContext } from "../../../context/HttpClientContext";

const BackgroundActivityContent = () => {
  const { data = [], isPending, error, refetch } = useListContext();
  const translate = useTranslate();
  const createPath = useCreatePath();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const panelId = useId();
  const active = data.some((record) =>
    ["pending", "running"].includes(record.status),
  );

  return (
    <>
      <Tooltip title={translate("backgroundActivity.title")}>
        <IconButton
          color="inherit"
          aria-label={translate("backgroundActivity.title")}
          aria-expanded={Boolean(anchor)}
          aria-haspopup="dialog"
          aria-controls={anchor ? panelId : undefined}
          onClick={(event) => setAnchor(event.currentTarget)}
        >
          <Badge variant="dot" color="info" invisible={!active}>
            <NotificationsNoneIcon />
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Box
          id={panelId}
          role="dialog"
          aria-label={translate("backgroundActivity.title")}
          sx={{ width: 440, maxWidth: "calc(100vw - 32px)" }}
        >
          <Stack
            direction="row"
            sx={{ p: 2, alignItems: "center", justifyContent: "space-between" }}
          >
            <Box>
              <Typography variant="h6">
                {translate("backgroundActivity.title")}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {translate("backgroundActivity.recent")}
              </Typography>
            </Box>
            <IconButton
              aria-label={translate("ra.action.close")}
              onClick={() => setAnchor(null)}
            >
              <CloseIcon />
            </IconButton>
          </Stack>
          <Divider />
          <Box sx={{ maxHeight: "60vh", overflowY: "auto" }}>
            {isPending && (
              <Box sx={{ p: 3, textAlign: "center" }}>
                <CircularProgress
                  size={24}
                  aria-label={translate("ra.message.loading")}
                />
              </Box>
            )}
            {error && (
              <Alert
                severity="error"
                action={
                  <Button onClick={() => void refetch()}>
                    {translate("ra.action.refresh")}
                  </Button>
                }
              >
                {translate("backgroundActivity.loadError")}
              </Alert>
            )}
            {!isPending && !error && data.length === 0 && (
              <Typography sx={{ p: 3 }} color="text.secondary">
                {translate("backgroundActivity.empty")}
              </Typography>
            )}
            {data.map((record) => {
              const running = ["pending", "running"].includes(record.status);
              const color =
                record.status === "failed"
                  ? "error"
                  : record.status === "completed"
                    ? "success"
                    : "info";
              const hasTotal =
                typeof record.totalSteps === "number" && record.totalSteps > 0;
              const progress = Math.min(
                100,
                Math.max(0, Number(record.progress) || 0),
              );
              return (
                <Box
                  key={record.id}
                  sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}
                >
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                    }}
                  >
                    <Typography
                      variant="subtitle2"
                      sx={{ overflowWrap: "anywhere" }}
                    >
                      {record.description ||
                        translate("backgroundActivity.process", {
                          id: record.id,
                        })}
                    </Typography>
                    <Chip
                      size="small"
                      color={color}
                      label={translate(
                        `backgroundActivity.status.${record.status}`,
                        { _: record.status },
                      )}
                    />
                  </Stack>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ my: 1, overflowWrap: "anywhere" }}
                  >
                    {record.phase}
                  </Typography>
                  {(running || hasTotal || record.status === "completed") && (
                    <LinearProgress
                      color={color}
                      variant={
                        running && !hasTotal ? "indeterminate" : "determinate"
                      }
                      value={progress}
                      aria-label={translate("backgroundActivity.progress")}
                    />
                  )}
                  <Stack
                    direction="row"
                    sx={{
                      mt: 1,
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      {hasTotal &&
                        translate("backgroundActivity.steps", {
                          done: record.doneSteps ?? 0,
                          total: record.totalSteps,
                        })}
                    </Typography>
                    <Button
                      component={Link}
                      to={createPath({
                        resource: "BackgroundProcess",
                        type: "show",
                        id: record.id,
                      })}
                      size="small"
                      onClick={() => setAnchor(null)}
                    >
                      {translate("backgroundActivity.viewDetails")}
                    </Button>
                  </Stack>
                </Box>
              );
            })}
          </Box>
          <Button
            component={Link}
            to={createPath({ resource: "BackgroundProcess", type: "list" })}
            fullWidth
            onClick={() => setAnchor(null)}
            sx={{ py: 1.5 }}
          >
            {translate("backgroundActivity.viewAll")}
          </Button>
        </Box>
      </Popover>
    </>
  );
};

const BackgroundActivityPanel = () => {
  // Polling is only the fallback: while the realtime bus is up the backend
  // pushes every change of the processes this panel shows.
  const { realtimeIsReady } = useHttpClientContext();
  return (
    <RealtimeListBase
      resource="BackgroundProcess"
      perPage={10}
      sort={{ field: "id", order: "DESC" }}
      disableSyncWithLocation
      queryOptions={{
        refetchInterval: realtimeIsReady === ReadyState.OPEN ? false : 20000,
      }}
    >
      <BackgroundActivityContent />
    </RealtimeListBase>
  );
};

export default BackgroundActivityPanel;

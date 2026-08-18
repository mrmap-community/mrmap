import { Box, LinearProgress, Typography } from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { HttpClientStatus, useHttpClientContext } from '../../context/HttpClientContext';



type StatusConfig = {
  frames: string[];
  title: string;
  text: string;
};

const statusConfig: Record<HttpClientStatus, StatusConfig> = {
  [HttpClientStatus.Idle]: {
    frames: [
      'mrmap_openapi_loading_01.png',
    ],
    title: 'Initializing MrMap',
    text: 'Preparing OpenAPI client…',
  },

  [HttpClientStatus.DownloadingSchema]: {
    frames: [
      'mrmap_openapi_loading_02.png',
      'mrmap_openapi_loading_03.png',
    ],
    title: 'Loading API schema',
    text: 'Downloading OpenAPI schema…',
  },

  [HttpClientStatus.InitializingClient]: {
    frames: [
      'mrmap_openapi_loading_05.png',
    ],
    title: 'Preparing API client',
    text: 'Processing API definitions…',
  },

  [HttpClientStatus.Ready]: {
    frames: [
      'mrmap_openapi_loading_06.png',
    ],
    title: 'Ready',
    text: 'OpenAPI client initialized.',
  },

  [HttpClientStatus.Error]: {
    frames: [
      'mr_map_500.png',
    ],
    title: 'Connection failed',
    text: 'Waiting for the API…',
  },
};

const MIN_FRAME_DURATION = 2000;

export interface LoadingOpenApiProps {
  canComplete: boolean;
  onComplete?: () => void;
}

const LoadingOpenApi = ({
  canComplete,
  onComplete
}: LoadingOpenApiProps) => {
  const {
    status,
    error,
  } = useHttpClientContext();

  /*
   * Real status comes immediately from the context.
   * displayStatus follows it, but guarantees that every
   * status is visible for at least MIN_FRAME_DURATION.
   */
  const [displayStatus, setDisplayStatus] =
    useState<HttpClientStatus>(status);

  const [frameIndex, setFrameIndex] = useState(0);

  const statusQueue = useRef<HttpClientStatus[]>([]);
  const processingQueue = useRef(false);
  const current = statusConfig[displayStatus];
  const currentFrame =
    current.frames[
      Math.min(frameIndex, current.frames.length - 1)
    ];
  
  /*
   * Queue every real status change.
   */
  useEffect(() => {
    if (
      status !== displayStatus &&
      !statusQueue.current.includes(status)
    ) {
      statusQueue.current.push(status);
    }
  }, [status, displayStatus]);

  /*
   * Process queued statuses one after another.
   *
   * This is intentionally UI-only. The HttpClientContext
   * itself is never delayed.
   */
  useEffect(() => {
    if (processingQueue.current) {
      return;
    }

    if (statusQueue.current.length === 0) {
      return;
    }

    processingQueue.current = true;

    const timeout = window.setTimeout(() => {
      const nextStatus = statusQueue.current.shift();

      if (nextStatus !== undefined) {
        setDisplayStatus(nextStatus);
      }

      processingQueue.current = false;
    }, MIN_FRAME_DURATION);

    return () => {
      window.clearTimeout(timeout);
      processingQueue.current = false;
    };
  }, [status, displayStatus]);


  /*
   * Start with the first frame whenever the displayed
   * status changes.
   */
  useEffect(() => {
    setFrameIndex(0);
  }, [displayStatus]);


  useEffect(() => {
    if (current.frames.length <= 1) {
      return;
    }

    const timeout = window.setTimeout(() => {
      setFrameIndex(currentIndex =>
        Math.min(
          currentIndex + 1,
          current.frames.length - 1
        )
      );
    }, MIN_FRAME_DURATION);

    return () => window.clearTimeout(timeout);
  }, [current.frames, frameIndex]);

  useEffect(() => {
    if (
      !canComplete ||
      displayStatus !== HttpClientStatus.Ready
    ) {
      return;
    }

    const timeout = window.setTimeout(() => {
      onComplete?.();
    }, MIN_FRAME_DURATION);

    return () => window.clearTimeout(timeout);
  }, [
    canComplete,
    displayStatus,
    onComplete,
  ]);

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: 2,
      }}
    >
      <Box
        sx={{
          width: '100%',
          maxWidth: 460,
          textAlign: 'center',
        }}
      >
        <Box
          sx={{
            height: 300,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 1,
          }}
        >
          <Box
            key={`${displayStatus}-${frameIndex}`}
            component="img"
            src={currentFrame}
            alt={current.text}
            sx={{
              width: 360,
              maxWidth: '90vw',
              maxHeight: 300,
              objectFit: 'contain',

              animation: 'mrmap-frame 150ms ease-out',

              '@keyframes mrmap-frame': {
                from: {
                  opacity: 0,
                  transform: 'translateY(4px) scale(0.98)',
                },
                to: {
                  opacity: 1,
                  transform: 'translateY(0) scale(1)',
                },
              },
            }}
          />
        </Box>

        <Typography
          variant="h5"
          sx={{
            fontWeight: 600,
            mb: 0.5,
          }}
        >
          {current.title}
        </Typography>

        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            mb: 3,
          }}
        >
          {current.text}
        </Typography>

        {displayStatus !== HttpClientStatus.Ready &&
          displayStatus !== HttpClientStatus.Error && (
            <LinearProgress
              sx={{
                height: 6,
                borderRadius: 10,

                '& .MuiLinearProgress-bar': {
                  borderRadius: 10,
                },
              }}
            />
          )}

        {current.frames.length > 1 && (
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              gap: 0.8,
              mt: 2,
            }}
          >
            {current.frames.map((_, index) => (
              <Box
                key={index}
                sx={{
                  width: index === frameIndex ? 18 : 6,
                  height: 6,
                  borderRadius: 10,
                  bgcolor:
                    index === frameIndex
                      ? 'primary.main'
                      : 'action.disabled',
                  transition: 'all 150ms ease',
                }}
              />
            ))}
          </Box>
        )}

        {displayStatus === HttpClientStatus.Error && (
          <Typography
            variant="caption"
            color="error"
            sx={{
              display: 'block',
              mt: 2,
            }}
          >
            {error?.message ?? 'Unable to connect to API'}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default LoadingOpenApi;
import { useEffect, useState } from "react";
import { useRecordContext, useTranslate } from "react-admin";

import { Box, Skeleton, Typography, type SxProps, type Theme } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import {
  API_BASE_URL,
  useHttpClientContext,
} from "../../../../context/HttpClientContext";
import { getAuthToken } from "../../../../providers/authProvider";

export const PreviewImage = ({
  src,
  alt,
  pending = false,
  loadingLabel,
  unavailableLabel,
  containerSx,
  imageSx,
}: {
  src?: string;
  alt: string;
  pending?: boolean;
  loadingLabel?: string;
  unavailableLabel?: string;
  containerSx?: SxProps<Theme>;
  imageSx?: SxProps<Theme>;
}) => {
  const translate = useTranslate();
  const [status, setStatus] = useState<"loading" | "loaded" | "error">(
    "loading",
  );
  const loading = pending || (Boolean(src) && status === "loading");

  return (
    <Box
      aria-busy={loading}
      sx={[{
        position: "relative",
        width: { xs: "100%", sm: 160 },
        height: 200,
        flexShrink: 0,
        borderRadius: 1,
        overflow: "hidden",
        bgcolor: "action.hover",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }, ...(Array.isArray(containerSx) ? containerSx : [containerSx ?? {}])]}
    >
      {(!src && !pending) || status === "error" ? (
        <Typography
          variant="body2"
          color="text.secondary"
          role="status"
          sx={{ px: 2, textAlign: "center" }}
        >
          {unavailableLabel ?? translate("serviceShow.previewUnavailable")}
        </Typography>
      ) : (
        <>
          {loading && (
            <Skeleton
              variant="rectangular"
              width="100%"
              height="100%"
              role="status"
              aria-label={loadingLabel ?? translate("serviceShow.previewLoading")}
              sx={{ position: "absolute", inset: 0 }}
            />
          )}
          {src && (
            <Box
              component="img"
              src={src}
              alt={alt}
              onLoad={() => setStatus("loaded")}
              onError={() => setStatus("error")}
              sx={[{
                display: "block",
                width: "100%",
                height: "100%",
                objectFit: "contain",
                visibility: loading ? "hidden" : "visible",
              }, ...(Array.isArray(imageSx) ? imageSx : [imageSx ?? {}])]}
            />
          )}
        </>
      )}
    </Box>
  );
};

const AuthenticatedPreviewImage = ({
  src,
  alt,
}: {
  src?: string;
  alt: string;
}) => {
  const { api } = useHttpClientContext();
  const [imageUrl, setImageUrl] = useState<string>();
  const { data, error } = useQuery({
    queryKey: ["servicePreviewImage", src],
    enabled: Boolean(api && src),
    retry: false,
    gcTime: 0,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      if (!api || !src) throw new Error("Preview unavailable");
      const endpoint = new URL(src, API_BASE_URL);
      if (endpoint.origin !== new URL(API_BASE_URL).origin)
        throw new Error("Preview must use the MrMap API");
      const token = getAuthToken()?.token;
      const response = await api.client.request<Blob>({
        url: endpoint.href,
        responseType: "blob",
        signal,
        headers: {
          Accept: "image/png",
          ...(token ? { Authorization: `Token ${token}` } : {}),
        },
      });
      if (!response.data.type.startsWith("image/"))
        throw new Error("Preview unavailable");
      return response.data;
    },
  });

  useEffect(() => {
    if (!data) return;
    const nextImageUrl = URL.createObjectURL(data);
    setImageUrl(nextImageUrl);
    return () => URL.revokeObjectURL(nextImageUrl);
  }, [data]);

  return (
    <PreviewImage
      key={imageUrl}
      src={error ? undefined : imageUrl}
      alt={alt}
      pending={Boolean(src) && !imageUrl && !error}
    />
  );
};

const ServicePreviewImage = ({
  authenticated = false,
}: {
  authenticated?: boolean;
}) => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;
  const src =
    typeof record.previewUrl === "string" && record.previewUrl.trim()
      ? record.previewUrl
      : undefined;

  const Component = authenticated ? AuthenticatedPreviewImage : PreviewImage;

  return (
    <Component
      key={`${record.id}:${src ?? ""}`}
      src={src}
      alt={translate("serviceShow.preview", {
        title: record.title ?? record.id,
      })}
    />
  );
};

export default ServicePreviewImage;

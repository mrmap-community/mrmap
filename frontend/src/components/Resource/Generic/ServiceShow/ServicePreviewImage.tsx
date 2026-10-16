import { Box, Skeleton, Typography } from "@mui/material";
import { useState } from "react";
import { useRecordContext, useTranslate } from "react-admin";

const PreviewImage = ({ src, alt }: { src?: string; alt: string }) => {
  const translate = useTranslate();
  const [status, setStatus] = useState<"loading" | "loaded" | "error">(
    "loading",
  );
  const loading = Boolean(src) && status === "loading";

  return (
    <Box
      aria-busy={loading}
      sx={{
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
      }}
    >
      {!src || status === "error" ? (
        <Typography
          variant="body2"
          color="text.secondary"
          role="status"
          sx={{ px: 2, textAlign: "center" }}
        >
          {translate("serviceShow.previewUnavailable")}
        </Typography>
      ) : (
        <>
          {loading && (
            <Skeleton
              variant="rectangular"
              width="100%"
              height="100%"
              role="status"
              aria-label={translate("serviceShow.previewLoading")}
              sx={{ position: "absolute", inset: 0 }}
            />
          )}
          <Box
            component="img"
            src={src}
            alt={alt}
            onLoad={() => setStatus("loaded")}
            onError={() => setStatus("error")}
            sx={{
              display: "block",
              width: "100%",
              height: "100%",
              objectFit: "contain",
              visibility: loading ? "hidden" : "visible",
            }}
          />
        </>
      )}
    </Box>
  );
};

const ServicePreviewImage = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;
  const src =
    typeof record.previewUrl === "string" && record.previewUrl.trim()
      ? record.previewUrl
      : undefined;

  return (
    <PreviewImage
      key={`${record.id}:${src ?? ""}`}
      src={src}
      alt={translate("serviceShow.preview", { title: record.title ?? record.id })}
    />
  );
};

export default ServicePreviewImage;

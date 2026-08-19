import { Breadcrumbs, Link, Typography } from '@mui/material';
import { useMemo } from 'react';
import { Link as RouterLink, useLocation } from 'react-router-dom';

const formatLabel = (segment: string): string => {
  const normalized = decodeURIComponent(segment).replace(/[-_]/g, ' ');

  return normalized
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

const isActionSegment = (segment: string): boolean =>
  ['list', 'show', 'edit', 'create', 'delete'].includes(segment.toLowerCase());

const BreadCrump = () => {
  const location = useLocation();

  const crumbs = useMemo(() => {
    const baseCrumb = { label: 'Home', to: '/' };
    const pathname = location.pathname.replace(/\/+$/, '') || '/';

    if (pathname === '/') {
      return [baseCrumb];
    }

    const segments = pathname.split('/').filter(Boolean);
    let currentPath = '';

    const routeCrumbs = segments.reduce<Array<{ label: string; to: string }>>((acc, segment) => {
      currentPath += `/${segment}`;

      if (isActionSegment(segment)) {
        acc.push({ label: formatLabel(segment), to: currentPath });
        return acc;
      }

      acc.push({
        label: /^\d+$/.test(segment) ? `#${segment}` : formatLabel(segment),
        to: currentPath,
      });

      return acc;
    }, []);

    return [baseCrumb, ...routeCrumbs];
  }, [location.pathname]);

  return (
    <Breadcrumbs aria-label="breadcrumb" sx={{ mb: 2, px: 1, pt: 1 }}>
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;

        if (isLast) {
          return (
            <Typography key={crumb.to} color="text.primary" sx={{ fontWeight: 600 }}>
              {crumb.label}
            </Typography>
          );
        }

        return (
          <Link
            key={crumb.to}
            component={RouterLink}
            to={crumb.to}
            underline="hover"
            color="inherit"
          >
            {crumb.label}
          </Link>
        );
      })}
    </Breadcrumbs>
  );
};

export default BreadCrump;
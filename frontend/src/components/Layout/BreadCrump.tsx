import { useMemo } from 'react';
import { useTranslate } from 'react-admin';
import { Link as RouterLink, useLocation } from 'react-router-dom';

import { Breadcrumbs, Link, Typography } from '@mui/material';

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
  const translate = useTranslate();

  const crumbs = useMemo(() => {
    const baseCrumb = { label: 'Home', to: '/' };

    // use this while iteration instead of regex to
    // Simplify this regular expression to reduce its runtime, 
    // as it has super-linear performance due to backtracking.
    const pathname = location.pathname;
    let end = pathname.length;

    while (end > 0 && pathname[end - 1] === '/') {
        end--;
    }

    const normalizedPathname = pathname.slice(0, end) || '/';

    if (normalizedPathname === '/') {
      return [baseCrumb];
    }

    const segments = normalizedPathname.split('/').filter(Boolean);
    let currentPath = '';

    const routeCrumbs = segments.reduce<Array<{ label: string; to: string }>>((acc, segment) => {
      currentPath += `/${segment}`;

      if (isActionSegment(segment)) {
        acc.push({ label: formatLabel(segment), to: currentPath });
        return acc;
      }

      acc.push({
        label: /^\d+$/.test(segment) ? `#${segment}` : translate(`resources.${segment}.plural`, { _: formatLabel(segment) }),
        to: currentPath,
      });

      return acc;
    }, []);

    return [baseCrumb, ...routeCrumbs];
  }, [location.pathname, translate]);

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

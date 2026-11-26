import { createElement, FC, ReactNode } from 'react';
import { useListContext, useLocaleState, useResourceContext, useTranslate } from 'react-admin';
import { Link, To } from 'react-router-dom';

import { Box, Card, Skeleton, Typography } from '@mui/material';
import { SparkLineChart } from '@mui/x-charts/SparkLineChart';

import { HistoryChartCore } from '../../Resource/Generic/History/HistoryChart';
import { useDashboardStatistics } from '../useDashboardStatistics';

interface Props {
    icon: FC<import("@mui/material").SvgIconProps>;
    to: To;
    title?: string;
    subtitle?: ReactNode;
    children?: ReactNode;
    compact?: boolean;
}

const CardWithIcon = ({
    icon,
    title,
    subtitle,
    to,
    children,
    compact = false,
}: Props) => {
    const resource = useResourceContext();
    const count = useListContext();
    const stats = useDashboardStatistics(resource ?? '', count);
    const translate = useTranslate();
    const [locale] = useLocaleState();
    const numberFormat = new Intl.NumberFormat(locale === 'de' ? 'de-DE' : 'en-GB');

    if (compact) {
        const translatedTitle = title
            ? translate(`resources.${resource}.plural`, { _: title })
            : translate(`resources.${resource}.name`, { _: resource });
        const values = stats.status === 'ready'
            ? stats.days.map(day => day.total).filter((value): value is number => value !== null)
            : [];
        const currentCount = count.error || count.isPending
            ? undefined
            : count.total;
        const delta = stats.status === 'ready' ? stats.inventory?.delta : undefined;
        const percent = stats.status === 'ready' ? stats.inventory?.percent : undefined;

        const deltaLabel = delta === undefined
            ? null
            : translate('dashboard.kpi.delta', {
                delta: `${delta >= 0 ? '+' : '−'}${numberFormat.format(Math.abs(delta))}`,
            });
        const percentLabel = percent === null
            ? translate('dashboard.kpi.noPercent')
            : percent !== undefined && Number.isFinite(percent)
                ? translate('dashboard.kpi.percent', {
                    percent: `${percent >= 0 ? '+' : '−'}${numberFormat.format(Math.abs(percent))}%`,
                })
                : null;

        return (
            <Card
                sx={{
                    height: '100%',
                    minHeight: 180,
                    display: 'flex',
                    flexDirection: 'column',
                    '& a': { textDecoration: 'none', color: 'inherit' },
                }}
            >
                <Link to={to} aria-label={translatedTitle}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 2, pt: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                            <Box sx={{ color: 'secondary.main', display: 'flex' }}>
                                {icon === undefined ? null : createElement(icon, { fontSize: 'medium' })}
                            </Box>
                            <Typography variant="subtitle2" noWrap title={translatedTitle}>
                                {translatedTitle}
                            </Typography>
                        </Box>
                    </Box>
                    <Box sx={{ px: 2, pt: 1 }}>
                        {count.isPending
                            ? <Skeleton variant="text" width={96} height={48} />
                            : <Typography variant="h4" component="p" sx={{ fontWeight: 600 }}>
                                {count.error || currentCount === undefined
                                    ? '—'
                                    : numberFormat.format(currentCount)}
                            </Typography>}
                        {(deltaLabel || percentLabel) && (
                            <Typography variant="caption" color="text.secondary">
                                {[deltaLabel, percentLabel].filter(Boolean).join(' · ')}
                            </Typography>
                        )}
                    </Box>
                </Link>
                <Box sx={{ height: 64, mt: 'auto', px: 1, pb: 1 }} role="img"
                    aria-label={translate('dashboard.kpi.sparkline', { resource: translatedTitle })}>
                    {stats.status === 'ready' && values.length > 1
                        ? <SparkLineChart
                            data={values}
                            height={64}
                            area
                            showHighlight
                            showTooltip
                            valueFormatter={(value) => value === null ? '—' : numberFormat.format(value)}
                            margin={{ top: 4, right: 8, bottom: 4, left: 8 }}
                            color="secondary.main"
                        />
                        : <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>
                            {translate(stats.status === 'ready'
                                ? 'dashboard.kpi.noTrend'
                                : {
                                    loading: 'historyChart.asking',
                                    error: 'historyChart.error',
                                    partial: 'historyChart.partial',
                                    unsupported: 'historyChart.noStatistics',
                                }[stats.status])}
                        </Typography>}
                </Box>
            </Card>
        );
    }

    const messages = {
        loading: 'historyChart.asking',
        error: 'historyChart.error',
        partial: 'historyChart.partial',
        unsupported: 'historyChart.noStatistics',
    };

    return (
        <Card
            sx={{
                minHeight: 52,
                display: 'flex',
                flexDirection: 'column',
                flex: '1',
                '& a': { textDecoration: 'none', color: 'inherit' },
            }}
        >
            <Box
                sx={{
                    position: 'relative',
                    overflow: 'hidden',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    '& .icon': { color: 'secondary.main' },
                    '&:before': {
                        position: 'absolute', top: '50%', left: 0, display: 'block',
                        content: `''`, height: '200%', aspectRatio: '1',
                        transform: 'translate(-30%, -60%)', borderRadius: '50%',
                        backgroundColor: 'secondary.main', opacity: 0.15,
                    },
                }}
            >
                <Box sx={{ width: '3em', className: 'icon', padding: '16px' }}>
                    {icon === undefined ? null : createElement(icon, { fontSize: 'large' })}
                </Box>
                <Link to={to}>
                    <Box sx={{ textAlign: 'right', paddingRight: '16px' }}>
                        <Typography color="textSecondary">{title}</Typography>
                        <Typography variant="h5" component="h2">{subtitle || ' '}</Typography>
                    </Box>
                </Link>
            </Box>
            {stats.status === 'ready'
                ? <HistoryChartCore changes={stats.days} height={100} />
                : <Typography variant="body2">{translate(messages[stats.status])}</Typography>}
            {children}
        </Card>
    );
};

export default CardWithIcon;

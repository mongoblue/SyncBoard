/**
 * 统一的 echarts 主题色板,与设计 token 保持一致。
 */

export interface EchartsTheme {
  palette: string[];
  textColor: string;
  textSecondary: string;
  borderColor: string;
  splitLineColor: string;
  axisLineColor: string;
  bgColor: string;
}

export const lightTheme: EchartsTheme = {
  palette: ['#0F766E', '#0969DA', '#9A6700', '#1A7F37', '#CF222E', '#8C959F'],
  textColor: '#1F2328',
  textSecondary: '#656D76',
  borderColor: '#D0D7DE',
  splitLineColor: '#E1E4E8',
  axisLineColor: '#D0D7DE',
  bgColor: '#FFFFFF',
};

export const darkTheme: EchartsTheme = {
  palette: ['#2DD4BF', '#58A6FF', '#D29922', '#3FB950', '#F85149', '#9198A1'],
  textColor: '#E6EDF3',
  textSecondary: '#9198A1',
  borderColor: '#30363D',
  splitLineColor: '#21262D',
  axisLineColor: '#30363D',
  bgColor: '#161B22',
};

export const getEchartsTheme = (): EchartsTheme => {
  const isDark =
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'dark';
  return isDark ? darkTheme : lightTheme;
};

export const getBaseEchartsOption = () => {
  const theme = getEchartsTheme();
  return {
    color: theme.palette,
    textStyle: {
      color: theme.textColor,
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
    },
    legend: {
      textStyle: { color: theme.textSecondary },
    },
    tooltip: {
      backgroundColor: theme.bgColor,
      borderColor: theme.borderColor,
      textStyle: { color: theme.textColor },
    },
    grid: {
      borderColor: theme.borderColor,
    },
    xAxis: {
      axisLine: { lineStyle: { color: theme.axisLineColor } },
      axisLabel: { color: theme.textSecondary },
      splitLine: { lineStyle: { color: theme.splitLineColor } },
    },
    yAxis: {
      axisLine: { lineStyle: { color: theme.axisLineColor } },
      axisLabel: { color: theme.textSecondary },
      splitLine: { lineStyle: { color: theme.splitLineColor } },
    },
  };
};

import type { GridApi } from 'ag-grid-community';

export type SmartTableDensity = 'compact' | 'comfortable';

export type SmartTableLayout = {
  columnState?: unknown[];
  filterModel?: Record<string, unknown>;
  rowHeight?: number;
  headerHeight?: number;
  density?: SmartTableDensity;
};

export const SMART_TABLE_DEFAULT_ROW_HEIGHT = 37;
export const SMART_TABLE_DEFAULT_HEADER_HEIGHT = 40;
export const SMART_TABLE_COMPACT_ROW_HEIGHT = 32;
export const SMART_TABLE_COMPACT_HEADER_HEIGHT = 36;

export const normalizeSmartTableText = (value: unknown): string =>
  String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();

export const getSmartTableStorageKey = (tableId: string, userKey: string): string =>
  `smart_table_layout:${tableId}:${userKey || 'anonymous'}`;

export const loadSmartTableLayout = (tableId: string, userKey: string): SmartTableLayout => {
  try {
    const raw = window.localStorage.getItem(getSmartTableStorageKey(tableId, userKey));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

export const saveSmartTableLayout = (
  tableId: string,
  userKey: string,
  layout: SmartTableLayout,
): void => {
  window.localStorage.setItem(
    getSmartTableStorageKey(tableId, userKey),
    JSON.stringify(layout),
  );
};

export const getSmartTableColumnState = (api: GridApi | null): unknown[] => {
  if (!api) return [];
  const anyApi = api as any;
  return typeof anyApi.getColumnState === 'function' ? anyApi.getColumnState() : [];
};

export const applySmartTableColumnState = (api: GridApi | null, state?: unknown[]): void => {
  if (!api || !Array.isArray(state) || state.length === 0) return;
  const anyApi = api as any;
  if (typeof anyApi.applyColumnState === 'function') {
    anyApi.applyColumnState({ state, applyOrder: true });
  }
};

export const getSmartTableFilterModel = (api: GridApi | null): Record<string, unknown> => {
  if (!api) return {};
  const anyApi = api as any;
  return typeof anyApi.getFilterModel === 'function' ? anyApi.getFilterModel() : {};
};

export const applySmartTableFilterModel = (
  api: GridApi | null,
  model?: Record<string, unknown>,
): void => {
  if (!api) return;
  const anyApi = api as any;
  if (typeof anyApi.setFilterModel === 'function') {
    anyApi.setFilterModel(model || {});
  }
};

export const setSmartTableColumnVisible = (
  api: GridApi | null,
  field: string,
  visible: boolean,
): void => {
  if (!api || !field) return;
  const anyApi = api as any;
  if (typeof anyApi.setColumnsVisible === 'function') {
    anyApi.setColumnsVisible([field], visible);
  }
};

export const resetSmartTableColumns = (api: GridApi | null): void => {
  if (!api) return;
  const anyApi = api as any;
  if (typeof anyApi.resetColumnState === 'function') {
    anyApi.resetColumnState();
  }
  if (typeof anyApi.setFilterModel === 'function') {
    anyApi.setFilterModel({});
  }
};

export const getSmartTableDisplayedFields = (api: GridApi | null): string[] => {
  if (!api) return [];
  const anyApi = api as any;
  const columns = typeof anyApi.getAllDisplayedColumns === 'function'
    ? anyApi.getAllDisplayedColumns()
    : [];

  return columns
    .map((column: any) => column?.getColDef?.().field)
    .filter((field: unknown): field is string => typeof field === 'string' && field.length > 0);
};

export const collectSmartTableUniqueValues = <T>(
  rows: T[],
  getter: (row: T) => string,
): string[] => {
  const values = new Set<string>();
  rows.forEach((row) => {
    const value = getter(row).trim();
    if (value) values.add(value);
  });
  return [...values].sort((a, b) => a.localeCompare(b));
};

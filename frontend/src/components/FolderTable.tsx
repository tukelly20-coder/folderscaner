import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef, GridApi, GridReadyEvent } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';

import {
  FolderRead,
  MaterialDocumentsResponse,
  MaterialFolderResponse,
  fetchMaterialFolder,
  fetchPlanFolderDocuments,
  fetchFolders,
  triggerScan,
} from '../services/api';
import { wsClient } from '../services/websocket';
import FolderEditor from './FolderEditor';
import './FolderTable.css';

declare global {
  interface Window {
    XLSX?: any;
  }
}

const statusOptions = [
  { value: 'active', label: 'Active' },
  { value: 'deleted', label: 'Deleted' },
  { value: 'pending', label: 'Pending' },
];

type ScannerLanguage = 'vi' | 'zh';

const scannerTranslations = {
  vi: {
    id: 'ID',
    month: 'Năm tháng',
    planCode: 'Mã phương án',
    spec: 'Quy cách',
    productType: 'Loại sản phẩm',
    customer: 'Khách hàng',
    salesperson: 'Nhân viên kinh doanh',
    drawingCodes: 'Mã bản vẽ',
    relativePath: 'Đường dẫn tương đối',
    smbPath: 'Đường dẫn SMB',
    status: 'Trạng thái',
    updated: 'Cập nhật',
    cannotConnect: 'Không thể kết nối máy chủ.',
  },
  zh: {
    id: 'ID',
    month: '年月',
    planCode: '方案编号',
    spec: '规格',
    productType: '产品类型',
    customer: '客户',
    salesperson: '业务员',
    drawingCodes: '图纸编号',
    relativePath: '相对路径',
    smbPath: 'SMB路径',
    status: '状态',
    updated: '更新时间',
    cannotConnect: '无法连接服务器。',
  },
};

const productTypes = [
  { code: 'SJT', zh: '软件图', vi: 'Bản vẽ tách chi tiết', keywords: ['软件图', '散件图', '皮带', '导条皮带', '护罩', '电机护罩', '下滚筒护罩', '设备门', '设备们', 'ban ve tach chi tiet', 'bản vẽ tách chi tiết', 'day belt', 'dây belt', 'day bang tai', 'dây băng tải', 'vo che', 'vỏ che', 'tam che', 'tấm che', 'cua thiet bi', 'cửa thiết bị'] },
  { code: 'WLJ', zh: '物料架', vi: 'Giá đựng vật liệu', keywords: ['物料架', '货架', '重型货架', '货架护栏', '精益管物料架', '推车', '设备车', '千层车', '料车', '台车', '周转架', '移动架', 'gia dung vat lieu', 'giá đựng vật liệu', 'ke hang', 'kệ hàng', 'gia hang', 'giá hàng', 'xe day', 'xe đẩy', 'xe thiet bi', 'xe thiết bị', 'xe vat lieu', 'xe vật liệu'] },
  { code: 'ZZC', zh: '周转车', vi: 'Xe trung chuyển', keywords: ['周转车', 'xe trung chuyen', 'xe trung chuyển'] },
  { code: 'GZT', zh: '工作台', vi: 'Bàn thao tác', keywords: ['工作台', 'ban thao tac', 'bàn thao tác'] },
  { code: 'WCP', zh: '无尘棚', vi: 'Phòng sạch', keywords: ['无尘棚', 'phong sach', 'phòng sạch'] },
  { code: 'LSX', zh: '流水线', vi: 'Băng tải', keywords: ['流水线', '接驳线', '皮带线', 'PVC皮带线', '输送线', 'bang tai', 'băng tải', 'day chuyen', 'dây chuyền'] },
  { code: 'ZWJ', zh: '转弯机', vi: 'Băng tải chuyển hướng 90,180', keywords: ['转弯机', '顶升移栽机', '移栽机', '顶升机', '移载机', '顶升移载', 'bang tai chuyen huong', 'băng tải chuyển hướng', 'may chuyen huong', 'máy chuyển hướng', 'may di chuyen ngang', 'máy di chuyển ngang'] },
  { code: 'GZL', zh: '改造类', vi: 'Cải tạo', keywords: ['改造类', 'cai tao', 'cải tạo'] },
  { code: 'BSX', zh: '倍速线', vi: 'Băng chuyền xích', keywords: ['倍速线', 'bang chuyen xich', 'băng chuyền xích'] },
  { code: 'WLL', zh: '围栏类', vi: 'Hàng rào', keywords: ['围栏类', '维兰类', '围栏', '护栏', '围栏立柱护罩', '立柱护罩', 'hang rao', 'hàng rào', 'lan can'] },
  { code: 'GTX', zh: '滚筒线', vi: 'Băng chuyền con lăn', keywords: ['滚筒线', 'bang chuyen con lan', 'băng chuyền con lăn'] },
  { code: 'ZHT', zh: '展会图', vi: 'Bản vẽ mặt bằng', keywords: ['展会图', 'ban ve mat bang', 'bản vẽ mặt bằng'] },
  { code: 'LHX', zh: '老化线', vi: 'Băng chuyền lão hóa', keywords: ['老化线', 'bang chuyen lao hoa', 'băng chuyền lão hóa'] },
];

const normalizeForMatch = (value: string): string =>
  value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

const PROJECT_FOLDER_REGEX = /^([A-Z][A-Z0-9]{0,7}-(\d{2})(0[1-9]|1[0-2])-\d{3}(?:-[A-Z]\d+)?)(?:$|[-_\s])/i;

const matchProjectFolderName = (name: string): RegExpMatchArray | null =>
  name.trim().match(PROJECT_FOLDER_REGEX);

const getScannerLanguage = (): ScannerLanguage => {
  const queryLanguage = new URLSearchParams(window.location.search).get('lang');
  const storedLanguage = window.localStorage.getItem('language');
  return queryLanguage === 'zh' || storedLanguage === 'zh' ? 'zh' : 'vi';
};

const getScannerUserKey = (): string => {
  const params = new URLSearchParams(window.location.search);
  const queryUser = params.get('user_id') || params.get('username');
  if (queryUser) return queryUser;

  try {
    const rawUser = window.localStorage.getItem('current_user') || window.sessionStorage.getItem('current_user') || '{}';
    const user = JSON.parse(rawUser);
    return String(user.user_id || user.id || user.username || user.full_name || 'anonymous');
  } catch {
    return 'anonymous';
  }
};

const getSmbRootStorageKey = (): string =>
  `scanner_smb_root:${getScannerUserKey()}`;

const getStoredSmbRoot = (): string =>
  window.localStorage.getItem(getSmbRootStorageKey()) || '';

const isValidScanRoot = (value: string): boolean => {
  const trimmed = value.trim();
  if (!trimmed) return false;
  return /^[a-zA-Z]:[\\/]/.test(trimmed) || /^\\\\[^\\/]+[\\/][^\\/]+/.test(trimmed);
};

const clearStoredRows = (
  setRows: React.Dispatch<React.SetStateAction<FolderRead[]>>,
  rowRef: React.MutableRefObject<FolderRead[]>,
  onFoldersChange?: (count: number) => void,
) => {
  rowRef.current = [];
  setRows([]);
  onFoldersChange?.(0);
};

type FolderTableProps = {
  refreshTrigger?: number;
  onFoldersChange?: (count: number) => void;
};

type ExcelViewerState = {
  fileName: string;
  workbook: any | null;
  sheetNames: string[];
  activeSheet: string;
  rows: string[][];
  loading: boolean;
  error: string | null;
};

const FolderTable: React.FC<FolderTableProps> = ({
  refreshTrigger = 0,
  onFoldersChange,
}) => {
  const [rowData, setRowData] = useState<FolderRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gridApi, setGridApi] = useState<GridApi | null>(null);
  const [editingFolder, setEditingFolder] = useState<FolderRead | null>(null);
  const [editingMode, setEditingMode] = useState<'rename' | 'move'>('rename');
  const [selectedFolder, setSelectedFolder] = useState<FolderRead | null>(null);
  const [language, setLanguage] = useState<ScannerLanguage>(() => getScannerLanguage());
  const [smbRoot, setSmbRoot] = useState(() => getStoredSmbRoot());
  const [smbDraft, setSmbDraft] = useState(() => getStoredSmbRoot());
  const [smbBusy, setSmbBusy] = useState(false);
  const [smbMessage, setSmbMessage] = useState<string | null>(null);
  const [materialCode, setMaterialCode] = useState('');
  const [materialDocs, setMaterialDocs] = useState<MaterialDocumentsResponse | null>(null);
  const [materialFolder, setMaterialFolder] = useState<MaterialFolderResponse | null>(null);
  const [materialFolderLoading, setMaterialFolderLoading] = useState(false);
  const [materialLoading, setMaterialLoading] = useState(false);
  const [materialError, setMaterialError] = useState<string | null>(null);
  const [excelViewer, setExcelViewer] = useState<ExcelViewerState | null>(null);
  const rowDataRef = useRef<FolderRead[]>([]);

  const labels = scannerTranslations[language];

  const extractQuyCach = (name: string): string => {
    const match = matchProjectFolderName(name);
    if (!match) return '';
    return name.trim().slice(match[1].length).replace(/^[-_\s]+/, '').trim();
  };

  const extractPlanMonth = (name: string): string => {
    const match = matchProjectFolderName(name);
    if (!match) return '';

    const [, , year, month] = match;
    return `${year}年${Number(month)}月`;
  };

  const formatProductType = (code: string): string => {
    const productType = productTypes.find((item) => item.code === code);
    if (!productType) return '';
    return language === 'zh'
      ? `${productType.code}${productType.zh}`
      : `${productType.code}${productType.zh} - ${productType.vi}`;
  };

  const detectProductType = (folder: FolderRead | undefined): string => {
    if (!folder) return '';
    const spec = extractQuyCach(folder.name || '');
    const drawingCodes = (folder.drawing_codes || []).join(' ');
    const source = `${folder.name || ''} ${spec} ${drawingCodes}`;
    const normalizedSource = normalizeForMatch(source);

    for (const productType of productTypes) {
      const codePattern = new RegExp(`(^|[^a-z0-9])P?${productType.code}(?=\\d|$|[^a-z0-9])`, 'i');
      if (codePattern.test(source)) {
        return formatProductType(productType.code);
      }
    }

    for (const productType of productTypes) {
      if (productType.keywords.some((keyword) => normalizedSource.includes(normalizeForMatch(keyword)))) {
        return formatProductType(productType.code);
      }
    }

    return '';
  };

  const areFoldersEqual = (a: FolderRead, b: FolderRead): boolean =>
    a.id === b.id &&
    a.name === b.name &&
    a.relative_path === b.relative_path &&
    a.absolute_path === b.absolute_path &&
    a.parent_id === b.parent_id &&
    a.status === b.status &&
    a.first_seen === b.first_seen &&
    a.last_seen === b.last_seen &&
    a.created_at === b.created_at &&
    a.updated_at === b.updated_at &&
    a.customer_name === b.customer_name &&
    a.salesperson_name === b.salesperson_name &&
    (a.drawing_codes || []).join('\u0001') === (b.drawing_codes || []).join('\u0001');

  const mergeFolderRows = (previousRows: FolderRead[], nextRows: FolderRead[]): FolderRead[] => {
    const previousById = new Map(previousRows.map((row) => [row.id, row]));
    return nextRows.map((nextRow) => {
      const previousRow = previousById.get(nextRow.id);
      return previousRow && areFoldersEqual(previousRow, nextRow) ? previousRow : nextRow;
    });
  };

  const columnDefs = useMemo<ColDef[]>(() => [
    {
      field: 'id',
      headerName: labels.id,
      width: 70,
      sortable: true,
      filter: false,
    },
    {
      field: 'plan_month',
      headerName: labels.month,
      width: 110,
      valueGetter: (params: any) => extractPlanMonth(params.data?.name || ''),
      sortable: true,
      filter: true,
    },
    {
      field: 'name',
      headerName: labels.planCode,
      width: 260,
      sortable: true,
      filter: true,
      valueFormatter: (params: any) => matchProjectFolderName(params.value || '')?.[1] || params.value,
    },
    {
      field: 'quy_cach',
      headerName: labels.spec,
      width: 240,
      valueGetter: (params: any) => extractQuyCach(params.data?.name || ''),
      sortable: true,
      filter: true,
    },
    {
      field: 'product_type',
      headerName: labels.productType,
      width: 210,
      valueGetter: (params: any) => detectProductType(params.data),
      sortable: true,
      filter: true,
    },
    {
      field: 'relative_path',
      headerName: labels.relativePath,
      width: 200,
      sortable: true,
      filter: true,
      hide: true,
    },
    {
      field: 'absolute_path',
      headerName: labels.smbPath,
      width: 200,
      sortable: false,
      filter: true,
      hide: true,
    },
    {
      field: 'status',
      headerName: labels.status,
      width: 130,
      cellRenderer: (params: any) => {
        const status = params.value as string;
        const label = statusOptions.find((s) => s.value === status)?.label || status;
        return `<span class="status-badge status-${status}">${label}</span>`;
      },
      sortable: true,
      filter: true,
      hide: true,
    },
    {
      field: 'updated_at',
      headerName: labels.updated,
      width: 150,
      valueFormatter: (params: any) =>
        new Date(params.value).toLocaleString('en-US'),
      sortable: true,
      hide: true,
    },
    {
      field: 'customer_name',
      headerName: labels.customer,
      width: 220,
      valueGetter: (params: any) => params.data?.customer_name || '',
      sortable: true,
      filter: true,
    },
    {
      field: 'salesperson_name',
      headerName: labels.salesperson,
      width: 180,
      valueGetter: (params: any) => params.data?.salesperson_name || '',
      sortable: true,
      filter: true,
    },
    {
      field: 'drawing_codes',
      headerName: labels.drawingCodes,
      flex: 1,
      valueGetter: (params: any) =>
        (params.data?.drawing_codes || []).join(', ') || '',
      sortable: true,
      filter: true,
    },
  ], [language, labels]);

  const onGridReady = useCallback((params: GridReadyEvent) => {
    setGridApi(params.api);
  }, []);

  const onCellValueChanged = useCallback((params: any) => {
    if (params.colDef.field === 'name') {
      const folder = params.data as FolderRead;
      setEditingFolder(folder);
      setEditingMode('rename');
    }
  }, []);

  const loadData = useCallback(async (rootOverride?: string) => {
    const isInitialLoad = rowDataRef.current.length === 0;
    const activeRoot = (rootOverride ?? smbRoot).trim();
    if (!activeRoot) {
      rowDataRef.current = [];
      setRowData([]);
      onFoldersChange?.(0);
      setError(null);
      setLoading(false);
      return;
    }

    if (isInitialLoad) {
      setLoading(true);
    }
    try {
      const res = await fetchFolders({
        limit: 500,
        status_filter: 'active',
        root: activeRoot,
      });
      setRowData((previousRows) => {
        const mergedRows = previousRows.length
          ? mergeFolderRows(previousRows, res.data)
          : res.data;
        const hasChanges = mergedRows.length !== previousRows.length
          || mergedRows.some((row, index) => row !== previousRows[index]);
        if (!hasChanges) {
          rowDataRef.current = previousRows;
          return previousRows;
        }
        rowDataRef.current = mergedRows;
        return mergedRows;
      });
      onFoldersChange?.(res.data.length);
      setError(null);
    } catch (err) {
      setError(labels.cannotConnect);
      console.error(err);
    } finally {
      if (isInitialLoad) {
        setLoading(false);
      }
    }
  }, [labels.cannotConnect, onFoldersChange, smbRoot]);

  const setupWebSocket = useCallback(() => {
    const cleanup = wsClient.onMessage((data) => {
      const message = data as any;
      setRowData((prev) => {
        switch (message.event) {
          case 'folder_created':
            loadDataRef.current();
            return prev;
          case 'folder_moved':
            loadDataRef.current();
            return prev.map((f) =>
              f.id === message.folder_id
                ? {
                    ...f,
                    name: message.name,
                    relative_path: message.relative_path,
                    absolute_path: message.absolute_path,
                  }
                : f,
            );
          case 'folder_renamed':
            loadDataRef.current();
            return prev.map((f) =>
              f.id === message.folder_id
                ? {
                    ...f,
                    name: message.name,
                    relative_path: message.relative_path,
                    absolute_path: message.absolute_path,
                  }
                : f,
            );
          case 'folder_modified':
            loadDataRef.current();
            return prev.map((f) =>
              f.id === message.folder_id
                ? { ...f, name: message.name }
                : f,
            );
          case 'folder_deleted':
            return prev.map((f) =>
              f.id === message.folder_id
                ? { ...f, status: 'deleted' }
                : f,
            );
          default:
            return prev;
        }
      });
    });
    return cleanup;
  }, []);

  const loadDataRef = useRef(loadData);

  useEffect(() => {
    loadDataRef.current = loadData;
  });

  useEffect(() => {
    const syncLanguage = () => setLanguage(getScannerLanguage());
    window.addEventListener('storage', syncLanguage);
    window.addEventListener('focus', syncLanguage);
    return () => {
      window.removeEventListener('storage', syncLanguage);
      window.removeEventListener('focus', syncLanguage);
    };
  }, []);

  useEffect(() => {
    loadDataRef.current();
  }, []);

  useEffect(() => {
    loadDataRef.current();
  }, [refreshTrigger]);

  useEffect(() => {
    if (import.meta.env.VITE_ENABLE_SCANNER_WS !== '1') {
      const intervalId = window.setInterval(() => {
        loadDataRef.current();
      }, 15000);
      return () => window.clearInterval(intervalId);
    }

    wsClient.connect();
    const cleanup = setupWebSocket();
    return () => {
      cleanup();
      wsClient.disconnect();
    };
  }, [setupWebSocket]);

  useEffect(() => {
    if (!gridApi) return;
    if (loading) {
      gridApi.showLoadingOverlay();
    } else {
      gridApi.hideOverlay();
    }
  }, [gridApi, loading]);

  const handleFolderUpdated = (updated: FolderRead) => {
    setRowData((prev) =>
      prev.map((f) => (f.id === updated.id ? updated : f)),
    );
    setEditingFolder(null);
  };

  const handleRowClick = (params: any) => {
    setSelectedFolder(params.data as FolderRead);
  };

  const handleSmbDraftChange = (value: string) => {
    setSmbDraft(value);
    if (!isValidScanRoot(value)) {
      setSmbRoot('');
      clearStoredRows(setRowData, rowDataRef, onFoldersChange);
      setError(null);
      setSmbMessage(
        value.trim()
          ? 'Duong dan phai co dang D:\\... hoac \\\\server\\share\\...'
          : 'Chua co SMB link nen bang dang de trong.',
      );
    } else {
      setSmbMessage(null);
    }
  };

  const handleSaveSmbRoot = async () => {
    const nextRoot = smbDraft.trim();
    setSmbBusy(true);
    setSmbMessage(null);
    try {
      if (!isValidScanRoot(nextRoot)) {
        if (nextRoot) {
          setSmbRoot('');
          clearStoredRows(setRowData, rowDataRef, onFoldersChange);
          setSmbMessage('Duong dan phai co dang D:\\... hoac \\\\server\\share\\...');
          return;
        }
      }
      if (nextRoot) {
        window.localStorage.setItem(getSmbRootStorageKey(), nextRoot);
      } else {
        window.localStorage.removeItem(getSmbRootStorageKey());
      }
      setSmbRoot(nextRoot);
      await loadData(nextRoot);
      setSmbMessage(nextRoot ? 'Da luu SMB link cho tai khoan nay.' : 'Da xoa SMB link, bang da de trong.');
    } finally {
      setSmbBusy(false);
    }
  };

  const handleScanSmbRoot = async () => {
    const nextRoot = smbDraft.trim();
    setSmbBusy(true);
    setSmbMessage(null);
    try {
      if (nextRoot) {
        window.localStorage.setItem(getSmbRootStorageKey(), nextRoot);
      } else {
        window.localStorage.removeItem(getSmbRootStorageKey());
      }
      setSmbRoot(nextRoot);
      if (!nextRoot) {
        await loadData('');
        setSmbMessage('Chua co SMB link nen khong quet. Bang da de trong.');
        return;
      }
      if (!isValidScanRoot(nextRoot)) {
        clearStoredRows(setRowData, rowDataRef, onFoldersChange);
        setSmbMessage('Duong dan phai co dang D:\\... hoac \\\\server\\share\\...');
        return;
      }

      const result = await triggerScan(nextRoot);
      const errors = result.data.results?.errors || [];
      if (errors.length) {
        setSmbMessage(String(errors[0]));
      } else {
        await loadData(nextRoot);
        const scan = result.data.results || {};
        setSmbMessage(
          `Da quet: moi ${scan.created || 0}, xoa ${scan.deleted || 0}, doi ten ${scan.renamed || 0}, sua ${scan.modified || 0}.`,
        );
      }
    } catch (err: any) {
      setSmbMessage(getApiErrorMessage(err, 'Khong the quet SMB link'));
    } finally {
      setSmbBusy(false);
    }
  };

  const getPlanCode = (folder: FolderRead): string => {
    const name = String(folder.name || '').trim();
    const match = matchProjectFolderName(name);
    if (match) return match[1];
    return (folder.drawing_codes || []).find((code) => String(code || '').trim()) || name;
  };

  const getMaterialIcon = (type?: string, isDir = false): string => {
    if (isDir) return 'folder';
    if (type === 'pdf') return 'PDF';
    if (type === 'bom') return 'XLS';
    if (type === 'cad') return 'CAD';
    if (type === 'drawing') return 'DWG';
    return 'FILE';
  };

  const getMaterialTypeLabel = (type?: string, isDir = false): string => {
    if (isDir) return 'Folder';
    if (type === 'pdf') return 'PDF';
    if (type === 'bom') return 'BOM';
    if (type === 'cad') return 'CAD';
    if (type === 'drawing') return 'Drawing';
    return 'File';
  };

  const formatFileSize = (value?: number): string => {
    const bytes = Number(value || 0);
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  };

  const formatDateTime = (value?: string): string => {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(language === 'zh' ? 'zh-CN' : 'vi-VN');
  };

  const getApiErrorMessage = (err: any, fallback: string): string => {
    const data = err?.response?.data;
    if (typeof data?.message === 'string') return data.message;
    if (typeof data?.detail === 'string') return data.detail;
    return err?.message || fallback;
  };

  const getSheetRows = (workbook: any, sheetName: string): string[][] => {
    const worksheet = workbook?.Sheets?.[sheetName];
    if (!worksheet || !window.XLSX?.utils?.sheet_to_json) return [];
    const rows = window.XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: '' }) as any[][];
    return rows
      .slice(0, 300)
      .map((row) => row.slice(0, 60).map((cell) => (cell == null ? '' : String(cell))));
  };

  const openExcelViewer = async (fileName: string, viewUrl: string) => {
    if (!viewUrl) return;
    setExcelViewer({
      fileName,
      workbook: null,
      sheetNames: [],
      activeSheet: '',
      rows: [],
      loading: true,
      error: null,
    });

    try {
      if (!window.XLSX) {
        throw new Error('Chua tai duoc SheetJS de doc Excel');
      }
      const response = await fetch(viewUrl);
      if (!response.ok) {
        throw new Error('Khong the doc file Excel');
      }
      const buffer = await response.arrayBuffer();
      const workbook = window.XLSX.read(buffer, { type: 'array' });
      const sheetNames = workbook.SheetNames || [];
      if (!sheetNames.length) {
        throw new Error('File Excel khong co sheet');
      }
      const activeSheet = sheetNames[0];
      setExcelViewer({
        fileName,
        workbook,
        sheetNames,
        activeSheet,
        rows: getSheetRows(workbook, activeSheet),
        loading: false,
        error: null,
      });
    } catch (err: any) {
      setExcelViewer((current) => current && {
        ...current,
        loading: false,
        error: err?.message || 'Loi doc file Excel',
      });
    }
  };

  const switchExcelSheet = (sheetName: string) => {
    setExcelViewer((current) => {
      if (!current?.workbook) return current;
      return {
        ...current,
        activeSheet: sheetName,
        rows: getSheetRows(current.workbook, sheetName),
      };
    });
  };

  const openMaterialFolder = async (listUrl: string) => {
    if (!listUrl) return;
    setMaterialFolderLoading(true);
    try {
      const res = await fetchMaterialFolder(listUrl);
      setMaterialFolder(res.data);
    } catch (err: any) {
      setMaterialError(getApiErrorMessage(err, 'Khong the mo thu muc SMB'));
    } finally {
      setMaterialFolderLoading(false);
    }
  };

  const handleRowDoubleClick = async (params: any) => {
    const folder = params.data as FolderRead | undefined;
    if (!folder) return;

    const code = getPlanCode(folder).trim();
    setMaterialCode(code);
    setMaterialDocs(null);
    setMaterialFolder(null);
    setMaterialError(null);
    setMaterialLoading(true);

    try {
      const res = await fetchPlanFolderDocuments(folder.id);
      setMaterialDocs(res.data);
    } catch (err: any) {
      setMaterialError(getApiErrorMessage(err, 'Khong tim thay tai lieu SMB'));
    } finally {
      setMaterialLoading(false);
    }
  };

  const closeMaterialModal = () => {
    setMaterialCode('');
    setMaterialDocs(null);
    setMaterialFolder(null);
    setMaterialError(null);
    setMaterialLoading(false);
    setMaterialFolderLoading(false);
    setExcelViewer(null);
  };

  return (
    <div className="folder-table-container">
      <div className="toolbar scanner-root-toolbar">
        <label className="scanner-root-label" htmlFor="scanner-smb-root">SMB link</label>
        <input
          id="scanner-smb-root"
          className="scanner-root-input"
          value={smbDraft}
          onChange={(event) => handleSmbDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              handleScanSmbRoot();
            }
          }}
          placeholder="\\\\server\\share\\du-an-ca-nhan"
          disabled={smbBusy}
        />
        <button type="button" onClick={handleSaveSmbRoot} disabled={smbBusy}>
          Luu
        </button>
        <button type="button" onClick={handleScanSmbRoot} disabled={smbBusy}>
          Quet
        </button>
        {smbMessage && <span className="scanner-root-message">{smbMessage}</span>}
        {error && <span className="error-banner">{error}</span>}
      </div>
      <div className="ag-theme-quartz folder-grid">
         <AgGridReact
           rowData={rowData}
           columnDefs={columnDefs}
           onGridReady={onGridReady}
          onCellValueChanged={onCellValueChanged}
           onRowClicked={handleRowClick}
           onRowDoubleClicked={handleRowDoubleClick}
           getRowId={(params) => String(params.data.id)}
           rowSelection="single"
           domLayout="normal"
           defaultColDef={{
             cellClass: 'col-with-border',
             headerClass: 'col-with-border',
           }}
         />
      </div>

      {editingFolder && (
        <div className="editor-overlay">
          <div className="editor-popup">
            <h3>Edit: {editingFolder.name}</h3>
            <FolderEditor
              folder={editingFolder}
              defaultMode={editingMode}
              onUpdated={handleFolderUpdated}
              onCancel={() => setEditingFolder(null)}
            />
          </div>
        </div>
      )}

      {materialCode && (
        <div className="material-modal-overlay" onMouseDown={closeMaterialModal}>
          <div className="material-modal" onMouseDown={(event) => event.stopPropagation()}>
            <div className="material-modal-header">
              <h3>Tai lieu ma phuong an: {materialCode}</h3>
              <button type="button" className="material-close-btn" onClick={closeMaterialModal}>
                x
              </button>
            </div>
            <div className="material-modal-body">
              {materialLoading && <div className="material-muted">Dang tai tai lieu...</div>}

              {materialError && (
                <div className="material-alert">
                  {materialError}
                </div>
              )}

              {materialDocs && !materialLoading && (
                <>
                  <div className="material-summary">
                    <span>{materialDocs.message || `Tim thay ${materialDocs.documents.length} tai lieu`}</span>
                    {materialDocs.resolved_code && materialDocs.resolved_code !== materialDocs.code && (
                      <span>Ma me: {materialDocs.resolved_code}</span>
                    )}
                  </div>

                  {materialDocs.erp_info?.rows?.length ? (
                    <section className="material-section">
                    <div className="material-section-title">ERP</div>
                      {materialDocs.erp_info.rows.map((row, index) => (
                        <div className="material-erp-item" key={`${row.sheet || 'erp'}-${index}`}>
                          {row.sheet && <strong>{row.sheet}</strong>}
                          <div className="material-erp-grid">
                            {Object.entries(row.values || {}).map(([key, value]) => (
                              <div key={key}>
                                <span>{key}</span>
                                <b>{value}</b>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </section>
                  ) : null}

                  {materialDocs.folders?.length ? (
                    <section className="material-section">
                      <div className="material-section-title">Thu muc SMB</div>
                      <div className="material-folder-buttons">
                        {materialDocs.folders.map((folder) => (
                          <button
                            type="button"
                            key={folder.list_url || folder.name}
                            className="material-folder-btn"
                            disabled={!folder.exists}
                            onClick={() => openMaterialFolder(folder.list_url)}
                          >
                            <span>{folder.name || 'Thu muc'}</span>
                            <small>{Number(folder.file_count || 0)} file</small>
                          </button>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {materialFolderLoading && <div className="material-muted">Dang mo thu muc...</div>}

                  {materialFolder && (
                    <section className="material-section">
                      <div className="material-section-title">
                        {materialFolder.folder_name || 'Thu muc'}
                      </div>
                      <div className="material-doc-list">
                        {(materialFolder.entries || []).map((entry) => (
                          <div className="material-doc-row" key={`${entry.name}-${entry.view_url || entry.list_url}`}>
                            <div className="material-file-icon">{getMaterialIcon(entry.type, entry.is_dir)}</div>
                            <div className="material-doc-main">
                              <strong>{entry.name}</strong>
                              <span>
                                {getMaterialTypeLabel(entry.type, entry.is_dir)}
                                {entry.size ? ` - ${formatFileSize(entry.size)}` : ''}
                                {entry.modified_at ? ` - ${formatDateTime(entry.modified_at)}` : ''}
                              </span>
                            </div>
                            <div className="material-actions">
                              {entry.is_dir ? (
                                <button type="button" onClick={() => openMaterialFolder(entry.list_url || '')}>
                                  Mo
                                </button>
                              ) : entry.type === 'bom' ? (
                                <button type="button" onClick={() => openExcelViewer(entry.name, entry.view_url || '')}>
                                  Mo
                                </button>
                              ) : (
                                <a href={entry.view_url || '#'} target="_blank" rel="noopener noreferrer">
                                  Mo
                                </a>
                              )}
                              {!entry.is_dir && (
                                <a href={entry.download_url || '#'}>Tai</a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {excelViewer && (
                    <section className="material-section excel-viewer-section">
                      <div className="excel-viewer-header">
                        <div className="material-section-title">{excelViewer.fileName || 'Excel Viewer'}</div>
                        <button type="button" className="excel-viewer-close" onClick={() => setExcelViewer(null)}>
                          x
                        </button>
                      </div>
                      {excelViewer.loading && <div className="material-muted">Dang tai file Excel...</div>}
                      {excelViewer.error && <div className="material-alert">{excelViewer.error}</div>}
                      {!excelViewer.loading && !excelViewer.error && (
                        <>
                          {excelViewer.sheetNames.length > 1 && (
                            <div className="excel-sheet-tabs">
                              {excelViewer.sheetNames.map((sheetName) => (
                                <button
                                  type="button"
                                  key={sheetName}
                                  className={sheetName === excelViewer.activeSheet ? 'active' : ''}
                                  onClick={() => switchExcelSheet(sheetName)}
                                >
                                  {sheetName}
                                </button>
                              ))}
                            </div>
                          )}
                          <div className="excel-table-wrap">
                            <table className="excel-table">
                              <tbody>
                                {excelViewer.rows.length ? (
                                  excelViewer.rows.map((row, rowIndex) => (
                                    <tr key={`${excelViewer.activeSheet}-${rowIndex}`}>
                                      {row.map((cell, cellIndex) => (
                                        <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                                      ))}
                                    </tr>
                                  ))
                                ) : (
                                  <tr>
                                    <td>Sheet trong</td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </section>
                  )}

                  {(materialDocs.documents || []).length ? (
                    <section className="material-section">
                      <div className="material-section-title">File</div>
                      <div className="material-doc-list">
                        {(materialDocs.documents || []).map((doc) => (
                          <div className={`material-doc-row${doc.exists ? '' : ' is-missing'}`} key={`${doc.name}-${doc.view_url}`}>
                            <div className="material-file-icon">{getMaterialIcon(doc.type)}</div>
                            <div className="material-doc-main">
                              <strong>{doc.name}</strong>
                              <span>
                                {getMaterialTypeLabel(doc.type)}
                                {doc.folder_name ? ` - ${doc.folder_name}` : ''}
                                {doc.exists ? '' : ' - server khong truy cap duoc file'}
                              </span>
                            </div>
                            <div className="material-actions">
                              {doc.type === 'bom' ? (
                                <button
                                  type="button"
                                  className={doc.exists ? '' : 'disabled'}
                                  disabled={!doc.exists}
                                  onClick={() => openExcelViewer(doc.name, doc.view_url || '')}
                                >
                                  Mo
                                </button>
                              ) : (
                                <a
                                  className={doc.exists ? '' : 'disabled'}
                                  href={doc.view_url || '#'}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  Mo
                                </a>
                              )}
                              <a className={doc.exists ? '' : 'disabled'} href={doc.download_url || '#'}>
                                Tai
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : (
                    <div className="material-alert">
                      {materialDocs.message || 'Khong tim thay tai lieu'}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default FolderTable;

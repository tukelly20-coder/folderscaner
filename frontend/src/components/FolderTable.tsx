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
  fetchUserSmbRoot,
  saveUserSmbRoot,
  triggerScan,
} from '../services/api';
import {
  SMART_TABLE_COMPACT_HEADER_HEIGHT,
  SMART_TABLE_COMPACT_ROW_HEIGHT,
  SMART_TABLE_DEFAULT_HEADER_HEIGHT,
  SMART_TABLE_DEFAULT_ROW_HEIGHT,
  SmartTableDensity,
  applySmartTableColumnState,
  applySmartTableFilterModel,
  getSmartTableColumnState,
  getSmartTableDisplayedFields,
  getSmartTableFilterModel,
  loadSmartTableLayout,
  normalizeSmartTableText,
  resetSmartTableColumns,
  saveSmartTableLayout,
  setSmartTableColumnVisible,
} from '../table/smartTable';
import { wsClient } from '../services/websocket';
import FolderEditor from './FolderEditor';
import './FolderTable.css';

const SCANNER_SMART_TABLE_ID = 'scanner-personal-projects';

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
    statusActive: 'Đang dùng',
    statusDeleted: 'Đã xóa',
    statusPending: 'Chờ xử lý',
    cannotConnect: 'Không thể kết nối máy chủ.',
    scanSettings: 'Cài đặt quét',
    save: 'Lưu',
    scan: 'Quét',
    closeSettings: 'Đóng cài đặt',
    smbPlaceholder: '\\\\server\\share hoặc D:\\du-an',
    searchPlaceholder: 'Tìm kiếm mã phương án, quy cách, khách hàng, mã bản vẽ...',
    clearSearch: 'Xóa tìm kiếm',
    invalidRoot: 'Đường dẫn phải có dạng D:\\... hoặc \\\\server\\share\\...',
    emptyNoLink: 'Chưa có SMB link nên bảng đang để trống.',
    savedRoot: 'Đã lưu SMB link cho tài khoản này.',
    clearedRoot: 'Đã xóa SMB link, bảng đã để trống.',
    noRootNoScan: 'Chưa có SMB link nên không quét. Bảng đã để trống.',
    copyCell: 'Đã copy ô đang chọn.',
    copyEmptyCell: 'Ô đang chọn không có dữ liệu.',
    copyRow: 'Đã copy dòng đang chọn.',
    scanFailed: 'Không thể quét SMB link',
    scanSummary: (scan: any) =>
      `Đã quét: mới ${scan.created || 0}, xóa ${scan.deleted || 0}, đổi tên ${scan.renamed || 0}, sửa ${scan.modified || 0}, cập nhật mã BV ${scan.document_cache_updated || 0}.`,
    editTitle: 'Sửa',
    materialTitle: 'Tài liệu mã phương án',
    loadingDocuments: 'Đang tải tài liệu...',
    foundDocuments: (count: number) => `Tìm thấy ${count} tài liệu`,
    materialSummary: (files: number, folders: number) => `Tìm thấy ${files} file và ${folders} thư mục trong SMB`,
    parentCode: 'Mã mẹ',
    smbFolders: 'Thư mục SMB',
    fileSection: 'File',
    folderFallback: 'Thư mục',
    fileCount: (count: number) => `${count} file`,
    openingFolder: 'Đang mở thư mục...',
    open: 'Mở',
    close: 'Đóng',
    download: 'Tải',
    folderType: 'Thư mục',
    drawingType: 'Bản vẽ',
    fileType: 'File',
    loadingExcel: 'Đang tải file Excel...',
    sheetEmpty: 'Sheet trống',
    excelLoadLibraryError: 'Chưa tải được SheetJS để đọc Excel',
    excelReadError: 'Không thể đọc file Excel',
    excelNoSheetError: 'File Excel không có sheet',
    excelError: 'Lỗi đọc file Excel',
    openSmbFolderError: 'Không thể mở thư mục SMB',
    documentsNotFoundError: 'Không tìm thấy tài liệu SMB',
    missingFileNote: 'server không truy cập được file',
    noDocuments: 'Không tìm thấy tài liệu',
    allStatus: 'Tất cả trạng thái',
    columns: 'Cột',
    resetLayout: 'Reset bảng',
    compact: 'Gọn',
    comfortable: 'Rộng',
    visibleColumns: 'Cột hiển thị',
    quickFilters: (count: number) => `${count} bộ lọc`,
    rowsShown: (shown: number, total: number) => `${shown}/${total} dòng`,
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
    statusActive: '有效',
    statusDeleted: '已删除',
    statusPending: '待处理',
    cannotConnect: '无法连接服务器。',
    scanSettings: '扫描设置',
    save: '保存',
    scan: '扫描',
    closeSettings: '关闭设置',
    smbPlaceholder: '\\\\server\\share 或 D:\\项目',
    searchPlaceholder: '搜索方案编号、规格、客户、图纸编号...',
    clearSearch: '清除搜索',
    invalidRoot: '路径格式必须为 D:\\... 或 \\\\server\\share\\...',
    emptyNoLink: '尚未设置SMB链接，表格为空。',
    savedRoot: '已为当前账号保存SMB链接。',
    clearedRoot: '已删除SMB链接，表格已清空。',
    noRootNoScan: '尚未设置SMB链接，未执行扫描。表格已清空。',
    copyCell: '已复制当前单元格。',
    copyEmptyCell: '当前单元格没有数据。',
    copyRow: '已复制当前行。',
    scanFailed: '无法扫描SMB链接',
    scanSummary: (scan: any) =>
      `扫描完成：新增 ${scan.created || 0}，删除 ${scan.deleted || 0}，重命名 ${scan.renamed || 0}，修改 ${scan.modified || 0}，更新图纸编号 ${scan.document_cache_updated || 0}。`,
    editTitle: '编辑',
    materialTitle: '方案资料',
    loadingDocuments: '正在加载资料...',
    foundDocuments: (count: number) => `找到 ${count} 个资料`,
    materialSummary: (files: number, folders: number) => `在SMB中找到 ${files} 个文件和 ${folders} 个文件夹`,
    parentCode: '母码',
    smbFolders: 'SMB文件夹',
    fileSection: '文件',
    folderFallback: '文件夹',
    fileCount: (count: number) => `${count} 个文件`,
    openingFolder: '正在打开文件夹...',
    open: '打开',
    close: '关闭',
    download: '下载',
    folderType: '文件夹',
    drawingType: '图纸',
    fileType: '文件',
    loadingExcel: '正在加载Excel文件...',
    sheetEmpty: 'Sheet为空',
    excelLoadLibraryError: '无法加载SheetJS读取Excel',
    excelReadError: '无法读取Excel文件',
    excelNoSheetError: 'Excel文件没有工作表',
    excelError: '读取Excel出错',
    openSmbFolderError: '无法打开SMB文件夹',
    documentsNotFoundError: '未找到SMB资料',
    missingFileNote: '服务器无法访问此文件',
    noDocuments: '未找到资料',
    allStatus: '全部状态',
    columns: '列',
    resetLayout: '重置表格',
    compact: '紧凑',
    comfortable: '舒适',
    visibleColumns: '显示列',
    quickFilters: (count: number) => `${count} 个筛选`,
    rowsShown: (shown: number, total: number) => `${shown}/${total} 行`,
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
  normalizeSmartTableText(value);

const PROJECT_FOLDER_REGEX = /^([A-Z][A-Z0-9]{0,7}-(\d{2})(0[1-9]|1[0-2])-\d{3}(?:-[A-Z]\d+)?)(?:$|[-_\s])/i;
const COPY_SUFFIX_REGEX = /(?:[-_\s]*(?:副本|复件|复制|copy|copie|duplicate)(?:\s*\(\d+\))?)+$/i;

const matchProjectFolderName = (name: string): RegExpMatchArray | null =>
  name.trim().match(PROJECT_FOLDER_REGEX);

const stripCopySuffix = (value: string): string => {
  let cleaned = value.trim();
  let previous = '';
  while (cleaned && cleaned !== previous) {
    previous = cleaned;
    cleaned = cleaned.replace(COPY_SUFFIX_REGEX, '').replace(/[-_\s]+$/g, '').trim();
  }
  return cleaned;
};

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
  const [scannerUserKey] = useState(() => getScannerUserKey());
  const [initialTableLayout] = useState(() =>
    loadSmartTableLayout(SCANNER_SMART_TABLE_ID, getScannerUserKey()),
  );
  const [smbRoot, setSmbRoot] = useState(() => getStoredSmbRoot());
  const [smbDraft, setSmbDraft] = useState(() => getStoredSmbRoot());
  const [smbBusy, setSmbBusy] = useState(false);
  const [smbMessage, setSmbMessage] = useState<string | null>(null);
  const [smartSearch, setSmartSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(false);
  const [columnPanelOpen, setColumnPanelOpen] = useState(false);
  const [columnUiVersion, setColumnUiVersion] = useState(0);
  const [density, setDensity] = useState<SmartTableDensity>(
    initialTableLayout.density || 'comfortable',
  );
  const [rowHeight, setRowHeight] = useState(
    Number(initialTableLayout.rowHeight) || SMART_TABLE_DEFAULT_ROW_HEIGHT,
  );
  const [headerHeight, setHeaderHeight] = useState(
    Number(initialTableLayout.headerHeight) || SMART_TABLE_DEFAULT_HEADER_HEIGHT,
  );
  const [materialCode, setMaterialCode] = useState('');
  const [materialDocs, setMaterialDocs] = useState<MaterialDocumentsResponse | null>(null);
  const [materialFolder, setMaterialFolder] = useState<MaterialFolderResponse | null>(null);
  const [materialFolderLoading, setMaterialFolderLoading] = useState(false);
  const [materialLoading, setMaterialLoading] = useState(false);
  const [materialError, setMaterialError] = useState<string | null>(null);
  const rowDataRef = useRef<FolderRead[]>([]);

  const labels = scannerTranslations[language];

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'scanner:openSettings') {
        setSettingsPanelOpen(true);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const extractQuyCach = (name: string): string => {
    const match = matchProjectFolderName(name);
    if (!match) return '';
    const spec = name.trim().slice(match[1].length).replace(/^[-_\s]+/, '').trim();
    return stripCopySuffix(spec);
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

  const getFolderCellValue = useCallback((folder: FolderRead | undefined, field?: string): string => {
    if (!folder || !field) return '';
    switch (field) {
      case 'id':
        return String(folder.id ?? '');
      case 'plan_month':
        return extractPlanMonth(folder.name || '');
      case 'name':
        return matchProjectFolderName(folder.name || '')?.[1] || folder.name || '';
      case 'quy_cach':
        return extractQuyCach(folder.name || '');
      case 'product_type':
        return detectProductType(folder);
      case 'relative_path':
        return folder.relative_path || '';
      case 'absolute_path':
        return folder.absolute_path || '';
      case 'status':
        return folder.status || '';
      case 'updated_at':
        if (!folder.updated_at) return '';
        {
          const parsed = new Date(folder.updated_at);
          return Number.isNaN(parsed.getTime())
            ? folder.updated_at
            : parsed.toLocaleString(language === 'zh' ? 'zh-CN' : 'vi-VN');
        }
      case 'customer_name':
        return folder.customer_name || '';
      case 'salesperson_name':
        return folder.salesperson_name || '';
      case 'drawing_codes':
        return (folder.drawing_codes || []).join(', ');
      default:
        return String((folder as any)[field] ?? '');
    }
  }, [language]);

  const getFolderRowClipboardText = useCallback((folder: FolderRead): string => {
    const fields = getSmartTableDisplayedFields(gridApi);
    return fields.map((field) => getFolderCellValue(folder, field)).join('\t');
  }, [getFolderCellValue, gridApi]);

  const getFolderSearchText = useCallback((folder: FolderRead): string => {
    const fields = [
      'id',
      'plan_month',
      'name',
      'quy_cach',
      'product_type',
      'customer_name',
      'salesperson_name',
      'drawing_codes',
      'relative_path',
      'absolute_path',
      'status',
    ];
    return fields.map((field) => getFolderCellValue(folder, field)).join(' ');
  }, [getFolderCellValue]);

  const writeClipboardText = useCallback(async (text: string) => {
    if (!text) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }, []);

  const copyFocusedFolderData = useCallback(async () => {
    const focusedCell = gridApi?.getFocusedCell();
    if (focusedCell) {
      const rowNode = gridApi?.getDisplayedRowAtIndex(focusedCell.rowIndex);
      const folder = rowNode?.data as FolderRead | undefined;
      const field = focusedCell.column.getColDef().field;
      const value = getFolderCellValue(folder, field);
      await writeClipboardText(value);
      setSmbMessage(value ? labels.copyCell : labels.copyEmptyCell);
      return;
    }

    if (selectedFolder) {
      await writeClipboardText(getFolderRowClipboardText(selectedFolder));
      setSmbMessage(labels.copyRow);
    }
  }, [getFolderCellValue, getFolderRowClipboardText, gridApi, labels, selectedFolder, writeClipboardText]);

  const getFolderFreshnessTime = (folder?: FolderRead): number => {
    const value = folder?.last_seen || folder?.updated_at || folder?.created_at || '';
    const parsed = new Date(value).getTime();
    return Number.isNaN(parsed) ? 0 : parsed;
  };

  const columnDefs = useMemo<ColDef[]>(() => [
    {
      field: 'id',
      headerName: labels.id,
      width: 70,
      sortable: true,
      comparator: (_a: number, _b: number, nodeA: any, nodeB: any) =>
        getFolderFreshnessTime(nodeA?.data) - getFolderFreshnessTime(nodeB?.data),
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
        const label = status === 'active'
          ? labels.statusActive
          : status === 'deleted'
            ? labels.statusDeleted
            : status === 'pending'
              ? labels.statusPending
              : statusOptions.find((s) => s.value === status)?.label || status;
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

  const persistSmartTableLayout = useCallback((apiOverride?: GridApi | null) => {
    const activeApi = apiOverride || gridApi;
    saveSmartTableLayout(SCANNER_SMART_TABLE_ID, scannerUserKey, {
      columnState: getSmartTableColumnState(activeApi),
      filterModel: getSmartTableFilterModel(activeApi),
      rowHeight,
      headerHeight,
      density,
    });
    setColumnUiVersion((version) => version + 1);
  }, [density, gridApi, headerHeight, rowHeight, scannerUserKey]);

  const restoreSmartTableLayout = useCallback((api: GridApi) => {
    applySmartTableColumnState(api, initialTableLayout.columnState);
    applySmartTableFilterModel(api, initialTableLayout.filterModel);
    setColumnUiVersion((version) => version + 1);
  }, [initialTableLayout]);

  const onGridReady = useCallback((params: GridReadyEvent) => {
    setGridApi(params.api);
    restoreSmartTableLayout(params.api);
  }, [restoreSmartTableLayout]);

  const handleResetSmartTableLayout = useCallback(() => {
    resetSmartTableColumns(gridApi);
    setSmartSearch('');
    setStatusFilter('');
    setDensity('comfortable');
    setRowHeight(SMART_TABLE_DEFAULT_ROW_HEIGHT);
    setHeaderHeight(SMART_TABLE_DEFAULT_HEADER_HEIGHT);
    saveSmartTableLayout(SCANNER_SMART_TABLE_ID, scannerUserKey, {
      rowHeight: SMART_TABLE_DEFAULT_ROW_HEIGHT,
      headerHeight: SMART_TABLE_DEFAULT_HEADER_HEIGHT,
      density: 'comfortable',
    });
    setColumnUiVersion((version) => version + 1);
  }, [gridApi, scannerUserKey]);

  const handleDensityChange = useCallback((nextDensity: SmartTableDensity) => {
    setDensity(nextDensity);
    setRowHeight(nextDensity === 'compact' ? SMART_TABLE_COMPACT_ROW_HEIGHT : SMART_TABLE_DEFAULT_ROW_HEIGHT);
    setHeaderHeight(nextDensity === 'compact' ? SMART_TABLE_COMPACT_HEADER_HEIGHT : SMART_TABLE_DEFAULT_HEADER_HEIGHT);
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
    let cancelled = false;
    fetchUserSmbRoot(scannerUserKey)
      .then((res) => {
        if (cancelled) return;
        const savedRoot = res.data?.smb_root?.trim() || '';
        if (!savedRoot) return;
        window.localStorage.setItem(getSmbRootStorageKey(), savedRoot);
        setSmbDraft(savedRoot);
        setSmbRoot(savedRoot);
        loadDataRef.current(savedRoot);
      })
      .catch((err) => {
        console.error(err);
      });

    return () => {
      cancelled = true;
    };
  }, [scannerUserKey]);

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

  useEffect(() => {
    const anyApi = gridApi as any;
    if (typeof anyApi?.resetRowHeights === 'function') {
      anyApi.resetRowHeights();
    }
    if (gridApi) {
      persistSmartTableLayout(gridApi);
    }
  }, [density, gridApi, headerHeight, persistSmartTableLayout, rowHeight]);

  useEffect(() => {
    const handleCopyShortcut = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'c') return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, textarea, [contenteditable="true"]')) return;
      if (!target?.closest('.folder-table-container')) return;
      if (!gridApi) return;

      event.preventDefault();
      copyFocusedFolderData();
    };

    document.addEventListener('keydown', handleCopyShortcut);
    return () => document.removeEventListener('keydown', handleCopyShortcut);
  }, [copyFocusedFolderData, gridApi]);

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
          ? labels.invalidRoot
          : labels.emptyNoLink,
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
          setSmbMessage(labels.invalidRoot);
          return;
        }
      }
      if (nextRoot) {
        window.localStorage.setItem(getSmbRootStorageKey(), nextRoot);
      } else {
        window.localStorage.removeItem(getSmbRootStorageKey());
      }
      await saveUserSmbRoot(scannerUserKey, nextRoot);
      setSmbRoot(nextRoot);
      await loadData(nextRoot);
      setSmbMessage(nextRoot ? labels.savedRoot : labels.clearedRoot);
    } finally {
      setSmbBusy(false);
    }
  };

  const handleScanSmbRoot = async () => {
    const nextRoot = smbDraft.trim();
    setSmbBusy(true);
    setSmbMessage(null);
    try {
      if (!nextRoot) {
        window.localStorage.removeItem(getSmbRootStorageKey());
        await saveUserSmbRoot(scannerUserKey, '');
        setSmbRoot('');
        await loadData('');
        setSmbMessage(labels.noRootNoScan);
        return;
      }
      if (!isValidScanRoot(nextRoot)) {
        setSmbRoot('');
        clearStoredRows(setRowData, rowDataRef, onFoldersChange);
        setSmbMessage(labels.invalidRoot);
        return;
      }

      window.localStorage.setItem(getSmbRootStorageKey(), nextRoot);
      await saveUserSmbRoot(scannerUserKey, nextRoot);
      setSmbRoot(nextRoot);
      const result = await triggerScan(nextRoot, true, scannerUserKey);
      const errors = result.data.results?.errors || [];
      if (errors.length) {
        setSmbMessage(String(errors[0]));
      } else {
        await loadData(nextRoot);
        const scan = result.data.results || {};
        setSmbMessage(labels.scanSummary(scan));
      }
    } catch (err: any) {
      setSmbMessage(getApiErrorMessage(err, labels.scanFailed));
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
    if (isDir) return labels.folderType;
    if (type === 'pdf') return 'PDF';
    if (type === 'bom') return 'BOM';
    if (type === 'cad') return 'CAD';
    if (type === 'drawing') return labels.drawingType;
    return labels.fileType;
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

  const openExcelPreviewTab = (fileName: string, viewUrl: string, downloadUrl = '') => {
    if (!viewUrl) return;
    const url = new URL('/scanner/excel-preview', window.location.origin);
    url.searchParams.set('url', viewUrl);
    url.searchParams.set('name', fileName || 'Excel');
    if (downloadUrl) {
      url.searchParams.set('download', downloadUrl);
    }
    window.open(url.toString(), '_blank', 'noopener,noreferrer');
  };

  const openMaterialFolder = async (listUrl: string) => {
    if (!listUrl) return;
    setMaterialFolderLoading(true);
    try {
      const res = await fetchMaterialFolder(listUrl);
      setMaterialFolder(res.data);
    } catch (err: any) {
      setMaterialError(getApiErrorMessage(err, labels.openSmbFolderError));
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
      setMaterialError(getApiErrorMessage(err, labels.documentsNotFoundError));
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
  };

  const visibleRowData = useMemo(() => {
    const query = normalizeForMatch(smartSearch.trim());
    const terms = query.split(/\s+/).filter(Boolean);
    return rowData.filter((folder) => {
      if (statusFilter && folder.status !== statusFilter) return false;
      if (!terms.length) return true;

      const source = normalizeForMatch(getFolderSearchText(folder));
      return terms.every((term) => source.includes(term));
    });
  }, [getFolderSearchText, rowData, smartSearch, statusFilter]);

  const columnPanelItems = useMemo(() => {
    const state = getSmartTableColumnState(gridApi) as Array<{ colId?: string; hide?: boolean }>;
    const hiddenById = new Map(state.map((item) => [String(item.colId || ''), !!item.hide]));
    return columnDefs
      .map((column) => {
        const field = String(column.field || '');
        return {
          field,
          label: String(column.headerName || field),
          visible: gridApi ? !hiddenById.get(field) : column.hide !== true,
        };
      })
      .filter((item) => item.field);
  }, [columnDefs, columnUiVersion, gridApi]);

  const activeQuickFilterCount = [smartSearch, statusFilter].filter(Boolean).length;

  return (
    <div className="folder-table-container">
      <div className="scanner-control-panel">
        <div className="scanner-tool-row">
          <div className="scanner-search-group">
            <span className="scanner-search-icon" aria-hidden="true" />
            <input
              className="scanner-search-input"
              value={smartSearch}
              onChange={(event) => setSmartSearch(event.target.value)}
              placeholder={labels.searchPlaceholder}
            />
            {smartSearch && (
              <button
                type="button"
                className="scanner-search-clear"
                onClick={() => setSmartSearch('')}
                aria-label={labels.clearSearch}
              >
                x
              </button>
            )}
          </div>
          <div className="scanner-filter-group">
            <select
              className="scanner-filter-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">{labels.allStatus}</option>
              {statusOptions.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.value === 'active'
                    ? labels.statusActive
                    : status.value === 'deleted'
                      ? labels.statusDeleted
                      : status.value === 'pending'
                        ? labels.statusPending
                        : status.label}
                </option>
              ))}
            </select>
          </div>
          <div className="scanner-view-actions">
            <button
              type="button"
              className={columnPanelOpen ? 'is-active' : ''}
              onClick={() => setColumnPanelOpen((open) => !open)}
            >
              {labels.columns}
            </button>
            <button
              type="button"
              className={density === 'compact' ? 'is-active' : ''}
              onClick={() => handleDensityChange(density === 'compact' ? 'comfortable' : 'compact')}
            >
              {density === 'compact' ? labels.compact : labels.comfortable}
            </button>
            <button type="button" onClick={handleResetSmartTableLayout}>
              {labels.resetLayout}
            </button>
          </div>
          <div className="scanner-table-summary">
            <span>{labels.rowsShown(visibleRowData.length, rowData.length)}</span>
            {activeQuickFilterCount > 0 && <span>{labels.quickFilters(activeQuickFilterCount)}</span>}
          </div>
        </div>
        {(smbMessage || error) && (
          <div className="scanner-feedback-row">
            {smbMessage && <span className="scanner-root-message">{smbMessage}</span>}
            {error && <span className="error-banner">{error}</span>}
          </div>
        )}
      </div>
      {settingsPanelOpen && (
        <div className="scanner-settings-backdrop" onClick={() => setSettingsPanelOpen(false)}>
          <section
            className="scanner-settings-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="scanner-settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="scanner-settings-header">
              <div className="scanner-settings-title" id="scanner-settings-title">
                <span className="scanner-settings-title-icon" aria-hidden="true" />
                <strong>{labels.scanSettings}</strong>
              </div>
              <button
                type="button"
                className="scanner-settings-close"
                onClick={() => setSettingsPanelOpen(false)}
                aria-label={labels.closeSettings}
              >
                x
              </button>
            </div>
            <div className="scanner-settings-body">
              <div className="scanner-root-group">
                <label className="scanner-root-label" htmlFor="scanner-smb-root">SMB</label>
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
                  placeholder={labels.smbPlaceholder}
                  disabled={smbBusy}
                  autoFocus
                />
              </div>
              <div className="scanner-primary-actions">
                <button type="button" className="scanner-action-button" onClick={handleSaveSmbRoot} disabled={smbBusy}>
                  <span className="scanner-action-icon scanner-action-icon-save" aria-hidden="true" />
                  {labels.save}
                </button>
                <button type="button" className="scanner-action-button scanner-action-button-primary" onClick={handleScanSmbRoot} disabled={smbBusy}>
                  <span className="scanner-action-icon scanner-action-icon-scan" aria-hidden="true" />
                  {labels.scan}
                </button>
              </div>
            </div>
            {(smbMessage || error) && (
              <div className="scanner-settings-feedback">
                {smbMessage && <span className="scanner-root-message">{smbMessage}</span>}
                {error && <span className="error-banner">{error}</span>}
              </div>
            )}
          </section>
        </div>
      )}
      {columnPanelOpen && (
        <div className="scanner-column-panel">
          <div className="scanner-column-panel-header">
            <strong>{labels.visibleColumns}</strong>
            <span>{columnPanelItems.filter((item) => item.visible).length}/{columnPanelItems.length}</span>
          </div>
          <div className="scanner-column-list">
            {columnPanelItems.map((column) => (
              <label className="scanner-column-item" key={column.field}>
                <input
                  type="checkbox"
                  checked={column.visible}
                  onChange={(event) => {
                    setSmartTableColumnVisible(gridApi, column.field, event.target.checked);
                    persistSmartTableLayout();
                  }}
                />
                <span>{column.label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
      <div className="ag-theme-quartz folder-grid">
         <AgGridReact
           rowData={visibleRowData}
           columnDefs={columnDefs}
           onGridReady={onGridReady}
           onColumnMoved={() => persistSmartTableLayout()}
           onColumnResized={(event) => {
             if ((event as any).finished) persistSmartTableLayout();
           }}
           onColumnVisible={() => persistSmartTableLayout()}
           onFilterChanged={() => persistSmartTableLayout()}
           onSortChanged={() => persistSmartTableLayout()}
          onCellValueChanged={onCellValueChanged}
           onRowClicked={handleRowClick}
           onRowDoubleClicked={handleRowDoubleClick}
           getRowId={(params) => String(params.data.id)}
           rowSelection="single"
           domLayout="normal"
           rowHeight={rowHeight}
           headerHeight={headerHeight}
           defaultColDef={{
             sortable: true,
             resizable: true,
             filter: true,
             cellClass: 'col-with-border',
             headerClass: 'col-with-border',
           }}
         />
      </div>

      {editingFolder && (
        <div className="editor-overlay">
          <div className="editor-popup">
            <h3>{labels.editTitle}: {editingFolder.name}</h3>
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
              <h3>
                <span>{labels.materialTitle}</span>
                <b>{materialCode}</b>
              </h3>
              <button type="button" className="material-close-btn" onClick={closeMaterialModal} aria-label={labels.close}>
                x
              </button>
            </div>
            <div className="material-modal-body">
              {materialLoading && <div className="material-muted">{labels.loadingDocuments}</div>}

              {materialError && (
                <div className="material-alert">
                  {materialError}
                </div>
              )}

              {materialDocs && !materialLoading && (
                <>
                  <div className="material-summary">
                    <span>{labels.materialSummary(materialDocs.documents.length, materialDocs.folders?.length || 0)}</span>
                    {materialDocs.resolved_code && materialDocs.resolved_code !== materialDocs.code && (
                      <span>{labels.parentCode}: {materialDocs.resolved_code}</span>
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
                      <div className="material-section-title">
                        <span>{labels.smbFolders}</span>
                        <small>{materialDocs.folders.length}</small>
                      </div>
                      <div className="material-folder-buttons">
                        {materialDocs.folders.map((folder) => (
                          <button
                            type="button"
                            key={folder.list_url || folder.name}
                            className="material-folder-btn"
                            disabled={!folder.exists}
                            onClick={() => openMaterialFolder(folder.list_url)}
                          >
                            <span>{folder.name || labels.folderFallback}</span>
                            <small>{labels.fileCount(Number(folder.file_count || 0))}</small>
                          </button>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {materialFolderLoading && <div className="material-muted">{labels.openingFolder}</div>}

                  {materialFolder && (
                    <section className="material-section">
                      <div className="material-section-title">
                        <span>{materialFolder.folder_name || labels.folderFallback}</span>
                        <small>{materialFolder.entries?.length || 0}</small>
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
                                  {labels.open}
                                </button>
                              ) : entry.type === 'bom' ? (
                                <button type="button" onClick={() => openExcelPreviewTab(entry.name, entry.view_url || '', entry.download_url || '')}>
                                  {labels.open}
                                </button>
                              ) : (
                                <a href={entry.view_url || '#'} target="_blank" rel="noopener noreferrer">
                                  {labels.open}
                                </a>
                              )}
                              {!entry.is_dir && (
                                <a href={entry.download_url || '#'}>{labels.download}</a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {(materialDocs.documents || []).length ? (
                    <section className="material-section">
                      <div className="material-section-title">
                        <span>{labels.fileSection}</span>
                        <small>{materialDocs.documents.length}</small>
                      </div>
                      <div className="material-doc-list">
                        {(materialDocs.documents || []).map((doc) => (
                          <div className={`material-doc-row${doc.exists ? '' : ' is-missing'}`} key={`${doc.name}-${doc.view_url}`}>
                            <div className="material-file-icon">{getMaterialIcon(doc.type)}</div>
                            <div className="material-doc-main">
                              <strong>{doc.name}</strong>
                              <span>
                                {getMaterialTypeLabel(doc.type)}
                                {doc.folder_name ? ` - ${doc.folder_name}` : ''}
                                {doc.size ? ` - ${formatFileSize(doc.size)}` : ''}
                                {doc.modified_at ? ` - ${formatDateTime(doc.modified_at)}` : ''}
                                {doc.exists ? '' : ` - ${labels.missingFileNote}`}
                              </span>
                            </div>
                            <div className="material-actions">
                              {doc.type === 'bom' ? (
                                <button
                                  type="button"
                                  className={doc.exists ? '' : 'disabled'}
                                  disabled={!doc.exists}
                                  onClick={() => openExcelPreviewTab(doc.name, doc.view_url || '', doc.download_url || '')}
                                >
                                  {labels.open}
                                </button>
                              ) : (
                                <a
                                  className={doc.exists ? '' : 'disabled'}
                                  href={doc.view_url || '#'}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  {labels.open}
                                </a>
                              )}
                              <a className={doc.exists ? '' : 'disabled'} href={doc.download_url || '#'}>
                                {labels.download}
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : (
                    <div className="material-alert">
                      {materialDocs.message || labels.noDocuments}
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

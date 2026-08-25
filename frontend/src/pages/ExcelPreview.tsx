import React, { useEffect, useMemo, useState } from 'react';
import './ExcelPreview.css';

declare global {
  interface Window {
    XLSX?: any;
  }
}

type PreviewLanguage = 'vi' | 'zh';

const previewText = {
  vi: {
    title: 'Xem trước Excel',
    loading: 'Đang tải file Excel...',
    download: 'Tải xuống',
    noFile: 'Thiếu đường dẫn file Excel.',
    noSheet: 'File Excel không có sheet.',
    loadLibraryError: 'Chưa tải được SheetJS để đọc Excel.',
    readError: 'Không thể đọc file Excel.',
    emptySheet: 'Sheet trống',
    limited: 'Chỉ hiển thị nhanh 300 dòng và 60 cột đầu để tránh đơ trình duyệt.',
  },
  zh: {
    title: 'Excel预览',
    loading: '正在加载Excel文件...',
    download: '下载',
    noFile: '缺少Excel文件路径。',
    noSheet: 'Excel文件没有工作表。',
    loadLibraryError: '无法加载SheetJS读取Excel。',
    readError: '无法读取Excel文件。',
    emptySheet: 'Sheet为空',
    limited: '仅快速显示前300行和前60列，避免浏览器卡顿。',
  },
};

const getPreviewLanguage = (): PreviewLanguage =>
  window.localStorage.getItem('language') === 'zh' ? 'zh' : 'vi';

const getSheetRows = (workbook: any, sheetName: string): string[][] => {
  const worksheet = workbook?.Sheets?.[sheetName];
  if (!worksheet || !window.XLSX?.utils?.sheet_to_json) return [];
  const rows = window.XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: '' }) as any[][];
  return rows
    .slice(0, 300)
    .map((row) => row.slice(0, 60).map((cell) => (cell == null ? '' : String(cell))));
};

const ExcelPreview: React.FC = () => {
  const labels = previewText[getPreviewLanguage()];
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const fileName = params.get('name') || 'Excel';
  const viewUrl = params.get('url') || '';
  const downloadUrl = params.get('download') || viewUrl;
  const [workbook, setWorkbook] = useState<any | null>(null);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState('');
  const [rows, setRows] = useState<string[][]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadWorkbook = async () => {
      setLoading(true);
      setError(null);
      try {
        if (!viewUrl) throw new Error(labels.noFile);
        if (!window.XLSX) throw new Error(labels.loadLibraryError);

        const response = await fetch(viewUrl);
        if (!response.ok) throw new Error(labels.readError);

        const buffer = await response.arrayBuffer();
        const nextWorkbook = window.XLSX.read(buffer, { type: 'array' });
        const nextSheetNames = nextWorkbook.SheetNames || [];
        if (!nextSheetNames.length) throw new Error(labels.noSheet);

        const nextActiveSheet = nextSheetNames[0];
        if (cancelled) return;
        setWorkbook(nextWorkbook);
        setSheetNames(nextSheetNames);
        setActiveSheet(nextActiveSheet);
        setRows(getSheetRows(nextWorkbook, nextActiveSheet));
      } catch (err: any) {
        if (!cancelled) setError(err?.message || labels.readError);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadWorkbook();
    return () => {
      cancelled = true;
    };
  }, [labels.loadLibraryError, labels.noFile, labels.noSheet, labels.readError, viewUrl]);

  const switchSheet = (sheetName: string) => {
    if (!workbook) return;
    setActiveSheet(sheetName);
    setRows(getSheetRows(workbook, sheetName));
  };

  return (
    <div className="excel-preview-page">
      <header className="excel-preview-header">
        <div className="excel-preview-title">
          <span>{labels.title}</span>
          <strong>{fileName}</strong>
        </div>
        <a className="excel-preview-download" href={downloadUrl || '#'} download>
          {labels.download}
        </a>
      </header>

      <main className="excel-preview-main">
        {loading && <div className="excel-preview-state">{labels.loading}</div>}
        {error && <div className="excel-preview-alert">{error}</div>}

        {!loading && !error && (
          <>
            {sheetNames.length > 1 && (
              <div className="excel-preview-tabs">
                {sheetNames.map((sheetName) => (
                  <button
                    type="button"
                    key={sheetName}
                    className={sheetName === activeSheet ? 'active' : ''}
                    onClick={() => switchSheet(sheetName)}
                  >
                    {sheetName}
                  </button>
                ))}
              </div>
            )}

            <div className="excel-preview-table-wrap">
              <table className="excel-preview-table">
                <tbody>
                  {rows.length ? (
                    rows.map((row, rowIndex) => (
                      <tr key={`${activeSheet}-${rowIndex}`}>
                        {row.map((cell, cellIndex) => (
                          <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                        ))}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td>{labels.emptySheet}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="excel-preview-note">{labels.limited}</div>
          </>
        )}
      </main>
    </div>
  );
};

export default ExcelPreview;

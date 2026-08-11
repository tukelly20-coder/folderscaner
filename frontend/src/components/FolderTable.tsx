import React, { useState, useCallback, useEffect, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef, GridApi, GridReadyEvent } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';

import {
  FolderRead,
  fetchFolders,
  exportFoldersExcel,
  scanDocuments,
} from '../services/api';
import { wsClient } from '../services/websocket';
import FolderEditor from './FolderEditor';
import './FolderTable.css';

const statusOptions = [
  { value: 'active', label: 'Active' },
  { value: 'deleted', label: 'Deleted' },
  { value: 'pending', label: 'Pending' },
];

type FolderTableProps = {
  refreshTrigger?: number;
  onFoldersChange?: (count: number) => void;
};

const FolderTable: React.FC<FolderTableProps> = ({
  refreshTrigger = 0,
  onFoldersChange,
}) => {
  const [rowData, setRowData] = useState<FolderRead[]>([]);
  const [customerMap, setCustomerMap] = useState<Record<string, string>>({});
  const [drawingCodesMap, setDrawingCodesMap] = useState<Record<string, string[]>>({});
  const [salespersonMap, setSalespersonMap] = useState<Record<string, string>>({});
  const customerMapRef = useRef(customerMap);
  const drawingCodesMapRef = useRef(drawingCodesMap);
  const salespersonMapRef = useRef(salespersonMap);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gridApi, setGridApi] = useState<GridApi | null>(null);
  const [editingFolder, setEditingFolder] = useState<FolderRead | null>(null);
  const [editingMode, setEditingMode] = useState<'rename' | 'move'>('rename');
  const [selectedFolder, setSelectedFolder] = useState<FolderRead | null>(null);
  const loadingCustomerNames = useRef(false);

  const extractQuyCach = (name: string): string => {
    if (name.length > 17) {
      return name.substring(17).trim();
    }
    return '';
  };

  const [columnDefs] = useState<ColDef[]>([
    {
      field: 'id',
      headerName: 'ID',
      width: 70,
      sortable: true,
      filter: false,
    },
    {
      field: 'name',
      headerName: 'Mã Phương án',
      width: 260,
      sortable: true,
      filter: true,
      valueFormatter: (params: any) => params.value.substring(0, 16),
    },
    {
      field: 'quy_cach',
      headerName: 'Quy cách',
      width: 240,
      valueGetter: (params: any) => extractQuyCach(params.data?.name || ''),
      sortable: true,
      filter: true,
    },
    {
      field: 'relative_path',
      headerName: 'Relative Path',
      width: 200,
      sortable: true,
      filter: true,
      hide: true,
    },
    {
      field: 'absolute_path',
      headerName: 'SMB Path',
      width: 200,
      sortable: false,
      filter: true,
      hide: true,
    },
    {
      field: 'status',
      headerName: 'Status',
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
      headerName: 'Updated',
      width: 150,
      valueFormatter: (params: any) =>
        new Date(params.value).toLocaleString('en-US'),
      sortable: true,
      hide: true,
    },
    {
      field: 'customer_name',
      headerName: 'Khách hàng',
      width: 220,
      valueGetter: (params: any) => params.data?.customer_name || '',
      sortable: true,
      filter: true,
    },
    {
      field: 'salesperson_name',
      headerName: 'Nhân viên kinh doanh',
      width: 180,
      valueGetter: (params: any) => params.data?.salesperson_name || '',
      sortable: true,
      filter: true,
    },
    {
      field: 'drawing_codes',
      headerName: 'Mã bản vẽ',
      flex: 1,
      valueGetter: (params: any) =>
        (params.data?.drawing_codes || []).join(', ') || '',
      sortable: true,
      filter: true,
    },
  ]);

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

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchFolders({ limit: 500, status_filter: 'active' });
      const enriched = res.data.map((f) => ({
        ...f,
        customer_name: customerMapRef.current[f.relative_path] || f.customer_name,
        salesperson_name: salespersonMapRef.current[f.relative_path] || f.salesperson_name,
        drawing_codes: drawingCodesMapRef.current[f.relative_path] || f.drawing_codes,
      }));
      setRowData(enriched);
      onFoldersChange?.(res.data.length);
      setError(null);
    } catch (err) {
      setError('Cannot connect to server.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [onFoldersChange]);

  const loadCustomerNames = useCallback(async () => {
    if (loadingCustomerNames.current) return;
    loadingCustomerNames.current = true;
    try {
      const res = await scanDocuments();
      const customerMapLocal: Record<string, string> = {};
      const drawingCodesMapLocal: Record<string, string[]> = {};
      const salespersonMapLocal: Record<string, string> = {};
      for (const item of res.data.results) {
        if (!item.a0_folder_path) continue;
        if (item.customer_name) {
          customerMapLocal[item.a0_folder_path] = item.customer_name;
        }
        if (item.salesperson_name) {
          salespersonMapLocal[item.a0_folder_path] = item.salesperson_name;
        }
        if (item.drawing_codes && item.drawing_codes.length > 0) {
          drawingCodesMapLocal[item.a0_folder_path] = item.drawing_codes;
        }
      }
      customerMapRef.current = customerMapLocal;
      drawingCodesMapRef.current = drawingCodesMapLocal;
      salespersonMapRef.current = salespersonMapLocal;
      setCustomerMap(customerMapLocal);
      setDrawingCodesMap(drawingCodesMapLocal);
      setSalespersonMap(salespersonMapLocal);
      setRowData((prev) =>
        prev.map((f) => ({
          ...f,
          customer_name: customerMapLocal[f.relative_path] || f.customer_name,
          salesperson_name: salespersonMapLocal[f.relative_path] || f.salesperson_name,
          drawing_codes: drawingCodesMapLocal[f.relative_path] || f.drawing_codes,
        })),
      );
    } catch (err) {
      console.error('Failed to load customer names:', err);
    } finally {
      loadingCustomerNames.current = false;
    }
  }, []);

  const setupWebSocket = useCallback(() => {
    const cleanup = wsClient.onMessage((data) => {
      const message = data as any;
      setRowData((prev) => {
        switch (message.event) {
          case 'folder_created':
            loadCustomerNamesRef.current();
            return [...prev, message as unknown as FolderRead];
          case 'folder_moved':
            loadCustomerNamesRef.current();
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
            loadCustomerNamesRef.current();
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
            loadCustomerNamesRef.current();
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
  const loadCustomerNamesRef = useRef(loadCustomerNames);

  useEffect(() => {
    loadDataRef.current = loadData;
    loadCustomerNamesRef.current = loadCustomerNames;
    customerMapRef.current = customerMap;
    drawingCodesMapRef.current = drawingCodesMap;
    salespersonMapRef.current = salespersonMap;
  });

  useEffect(() => {
    const init = async () => {
      await loadCustomerNamesRef.current();
      loadDataRef.current();
    };
    init();
  }, []);

  useEffect(() => {
    loadDataRef.current();
  }, [refreshTrigger]);

  useEffect(() => {
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

  return (
    <div className="folder-table-container">
      <div className="ag-theme-quartz folder-grid">
         <AgGridReact
           rowData={rowData}
           columnDefs={columnDefs}
           onGridReady={onGridReady}
           onCellValueChanged={onCellValueChanged}
           onRowClicked={handleRowClick}
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

    </div>
  );
};

export default FolderTable;

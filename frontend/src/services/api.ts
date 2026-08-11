import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
});

export interface FolderRead {
  id: number;
  name: string;
  relative_path: string;
  absolute_path: string;
  parent_id: number | null;
  status: 'active' | 'deleted' | 'pending';
  first_seen: string;
  last_seen: string;
  created_at: string;
  updated_at: string;
  children: FolderRead[];
  events: FolderEventRead[];
  customer_name?: string;
  salesperson_name?: string;
  drawing_codes?: string[];
}

export interface FolderEventRead {
  id: number;
  folder_id: number;
  event_type: 'created' | 'deleted' | 'modified' | 'renamed' | 'moved';
  old_name: string | null;
  new_name: string | null;
  old_path: string | null;
  new_path: string | null;
  detected_at: string;
  source: string | null;
}

export interface FolderUpdate {
  name?: string;
  relative_path?: string;
  absolute_path?: string;
  parent_id?: number;
  status?: 'active' | 'deleted' | 'pending';
}

export interface FolderMove {
  new_relative_path: string;
  new_name?: string;
}

export interface ApiError {
  error: string;
  message: string;
}

// Folder endpoints
export const fetchFolders = (params?: {
  skip?: number;
  limit?: number;
  status_filter?: string;
}) => api.get<FolderRead[]>('/folders', { params });

export const fetchFolder = (id: number) =>
  api.get<FolderRead>(`/folders/${id}`);

export const updateFolder = (id: number, data: FolderUpdate) =>
  api.put<FolderRead>(`/folders/${id}`, data);

export const moveFolder = (id: number, data: FolderMove) =>
  api.post<FolderRead>(`/folders/${id}/move`, data);

export const deleteFolder = (id: number) =>
  api.delete<FolderRead>(`/folders/${id}`);

// Event endpoints
export const fetchEvents = (params?: {
  skip?: number;
  limit?: number;
  folder_id?: number;
  event_type?: string;
}) => api.get<FolderEventRead[]>('/folder-events', { params });

// Scanner endpoints
export const fetchScannerStatus = () =>
  api.get<{ scan_interval: number; smb_root: string; excludes: string[]; running: boolean }>(
    '/scanner/status',
  );

export const updateScannerExcludes = (excludes: string[]) =>
  api.post<{ success: boolean; excludes: string[]; results: any }>(
    '/scanner/excludes',
    { excludes },
  );

export interface DocumentScanResult {
  a0_folder_path: string;
  a0_folder_name: string;
  customer_name: string | null;
  customer_subfolder_name: string | null;
  salesperson_name: string | null;
  found: boolean;
  drawing_codes: string[];
}

export interface DocumentScanResponse {
  root: string;
  total_scanned: number;
  results: DocumentScanResult[];
}

export const scanDocuments = (root?: string) =>
  api.post<DocumentScanResponse>('/documents/scan', null, {
    params: root ? { root } : undefined,
  });

export const triggerScan = () =>
  api.post<{ success: boolean; results: any }>('/scanner/scan');

export const exportFoldersExcel = () => {
  window.open('/api/folders/export/excel', '_blank');
};

export const isApiError = (err: unknown): err is { response: { data: ApiError } } =>
  typeof err === 'object' &&
  err !== null &&
  'response' in err &&
  typeof (err as any).response?.data?.error === 'string';

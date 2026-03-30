export interface SystemStatus {
  last_checked: string;
  last_error: string | null;
}

export interface Download {
  id: number;
  title: string;
  tmdb_id: string;
  file_size_bytes: number;
  status: 'pending_approval' | 'downloading' | 'queued' | 'completed' | 'error' | 'denied';
  added_date: string;
  aither_torrent_id: string;
  download_link: string;
  resolution: string;
  progress: number;
  eta_seconds: number;
}

export interface AppState {
  downloads: Download[];
  pending_groups: Record<string, Download[]>;
  pending_count: number;
  last_check: string;
  last_error: string | null;
}

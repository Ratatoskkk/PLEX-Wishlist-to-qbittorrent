export interface Download {
  id: number;
  title: string;
  tmdb_id: string;
  file_size_bytes: number;
  status: 'pending_approval' | 'downloading' | 'queued' | 'completed' | 'error' | 'denied' | 'insufficient_space';
  added_date: string;
  aither_torrent_id: string;
  download_link: string;
  resolution: string;
  progress: number;
  eta_seconds: number;
  poster_path: string | null;
  save_path: string | null;
  watched: number;
}

export interface TrackedEpisode {
  id: number;
  tmdb_id: string;
  show_title: string;
  season_num: number;
  episode_num: number;
  air_date: string;
  status: 'waiting' | 'polling' | 'downloaded' | 'give_up' | 'ignored';
  poster_path: string | null;
  media_type: 'episode' | 'movie';
}

export interface CleanupItem {
  id: number;
  title: string;
  poster_path: string | null;
  file_size_bytes: number;
  save_path: string;
  drive_label: string;
  resolution: string;
}

export interface ProgressUpdate {
  progress: number;
  eta_seconds: number;
  speed_mbps: number;
}

export interface AppState {
  downloads: Download[];
  pending_groups: Record<string, Download[]>;
  pending_count: number;
  upcoming: TrackedEpisode[];
  last_check: string;
  last_error: string | null;
}

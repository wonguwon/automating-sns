export interface UserResponse {
  id: number;
  email: string;
  displayName: string;
  createdAt: string;
}

export interface ProjectResponse {
  id: number;
  ownerId: number;
  name: string;
  createdAt: string;
}

export type JobType =
  | 'RSS_COLLECT'
  | 'CANDIDATE_SELECT'
  | 'DEEP_RESEARCH'
  | 'CARDNEWS_GENERATE'
  | 'COVER_IMAGE_GENERATE'
  | 'CARDNEWS_RENDER'
  | 'REEL_SCRIPT_GENERATE'
  | 'SCENE_IMAGE_GENERATE'
  | 'TTS_SYNTHESIZE'
  | 'REEL_RENDER';

export type JobStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';

export interface JobResponse {
  id: number;
  projectId: number;
  type: JobType;
  status: JobStatus;
  inputJson: string;
  resultJson: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

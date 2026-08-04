import type { JobResponse, JobType, ProjectResponse, UserResponse } from './types';

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjectsByOwner: (ownerId: number) =>
    request<ProjectResponse[]>(`/projects?ownerId=${ownerId}`),
  getProject: (id: number) => request<ProjectResponse>(`/projects/${id}`),
  createProject: (ownerId: number, name: string) =>
    request<ProjectResponse>('/projects', {
      method: 'POST',
      body: JSON.stringify({ ownerId, name }),
    }),
  getUser: (id: number) => request<UserResponse>(`/users/${id}`),
  createUser: (email: string, displayName: string) =>
    request<UserResponse>('/users', {
      method: 'POST',
      body: JSON.stringify({ email, displayName }),
    }),
  listJobsByProject: (projectId: number) =>
    request<JobResponse[]>(`/jobs?projectId=${projectId}`),
  getJob: (id: number) => request<JobResponse>(`/jobs/${id}`),
  createJob: (projectId: number, type: JobType, inputJson: string) =>
    request<JobResponse>('/jobs', {
      method: 'POST',
      body: JSON.stringify({ projectId, type, inputJson }),
    }),
};

export { ApiError };

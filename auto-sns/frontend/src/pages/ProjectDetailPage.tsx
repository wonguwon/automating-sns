import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { JobResponse, JobType, ProjectResponse } from '../api/types';

const JOB_TYPES: JobType[] = [
  'RSS_COLLECT',
  'CANDIDATE_SELECT',
  'DEEP_RESEARCH',
  'CARDNEWS_GENERATE',
  'COVER_IMAGE_GENERATE',
  'CARDNEWS_RENDER',
  'REEL_SCRIPT_GENERATE',
  'SCENE_IMAGE_GENERATE',
  'TTS_SYNTHESIZE',
  'REEL_RENDER',
];

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);

  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [jobType, setJobType] = useState<JobType>('RSS_COLLECT');
  const [inputJson, setInputJson] = useState('{}');
  const [error, setError] = useState<string | null>(null);

  async function loadAll() {
    setError(null);
    try {
      const [projectRes, jobsRes] = await Promise.all([
        api.getProject(projectId),
        api.listJobsByProject(projectId),
      ]);
      setProject(projectRes);
      setJobs(jobsRes);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err));
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function createJob() {
    setError(null);
    try {
      JSON.parse(inputJson);
    } catch {
      setError('inputJson이 올바른 JSON이 아닙니다.');
      return;
    }
    try {
      await api.createJob(projectId, jobType, inputJson);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err));
    }
  }

  return (
    <section>
      <h1>프로젝트 상세</h1>

      {error && <p className="error">{error}</p>}
      {!project && !error && <p>불러오는 중...</p>}

      {project && (
        <div>
          <p>
            <strong>{project.name}</strong> (id: {project.id}, owner: {project.ownerId})
          </p>

          <h2>Job 생성</h2>
          <div className="field-row">
            <label>
              타입
              <select value={jobType} onChange={(e) => setJobType(e.target.value as JobType)}>
                {JOB_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="field-row">
            <label>
              inputJson
              <textarea
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                rows={4}
              />
            </label>
          </div>
          <button onClick={createJob}>Job 생성</button>

          <h2>Job 목록</h2>
          <table>
            <thead>
              <tr>
                <th>id</th>
                <th>type</th>
                <th>status</th>
                <th>result / error</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.type}</td>
                  <td>{job.status}</td>
                  <td>
                    <pre>{job.errorMessage ?? job.resultJson ?? ''}</pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

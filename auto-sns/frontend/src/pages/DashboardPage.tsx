import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { ProjectResponse } from '../api/types';

export function DashboardPage() {
  const [ownerId, setOwnerId] = useState('1');
  const [projects, setProjects] = useState<ProjectResponse[] | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadProjects() {
    setError(null);
    setLoading(true);
    try {
      const list = await api.listProjectsByOwner(Number(ownerId));
      setProjects(list);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function createProject() {
    if (!newProjectName.trim()) return;
    setError(null);
    try {
      await api.createProject(Number(ownerId), newProjectName.trim());
      setNewProjectName('');
      await loadProjects();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err));
    }
  }

  return (
    <section>
      <h1>대시보드</h1>

      <div className="field-row">
        <label>
          Owner ID
          <input value={ownerId} onChange={(e) => setOwnerId(e.target.value)} />
        </label>
        <button onClick={loadProjects} disabled={loading}>
          프로젝트 불러오기
        </button>
      </div>

      <div className="field-row">
        <label>
          새 프로젝트 이름
          <input value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} />
        </label>
        <button onClick={createProject}>프로젝트 생성</button>
      </div>

      {error && <p className="error">{error}</p>}

      {projects && (
        <ul className="project-list">
          {projects.length === 0 && <li>프로젝트가 없습니다.</li>}
          {projects.map((project) => (
            <li key={project.id}>
              <Link to={`/projects/${project.id}`}>{project.name}</Link>
              <span className="muted"> (id: {project.id})</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

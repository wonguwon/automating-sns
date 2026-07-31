package ai.oneground.autosns.job;

import ai.oneground.autosns.domain.job.Job;
import ai.oneground.autosns.domain.job.JobRepository;
import ai.oneground.autosns.domain.job.JobStatus;
import ai.oneground.autosns.domain.project.Project;
import ai.oneground.autosns.domain.project.ProjectRepository;
import ai.oneground.autosns.job.dto.CreateJobRequest;
import ai.oneground.autosns.job.dto.JobResponse;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@RequiredArgsConstructor
public class JobService {

    private final JobRepository jobRepository;
    private final ProjectRepository projectRepository;

    @Transactional
    public JobResponse createJob(CreateJobRequest request) {
        Project project = projectRepository.findById(request.projectId())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "프로젝트를 찾을 수 없습니다: " + request.projectId()));

        Job job = Job.builder()
                .project(project)
                .type(request.type())
                .status(JobStatus.PENDING)
                .inputJson(request.inputJson())
                .build();

        return JobResponse.from(jobRepository.save(job));
    }

    @Transactional(readOnly = true)
    public JobResponse getJob(Long id) {
        Job job = jobRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "작업을 찾을 수 없습니다: " + id));
        return JobResponse.from(job);
    }

    @Transactional(readOnly = true)
    public List<JobResponse> listJobsByProject(Long projectId) {
        return jobRepository.findByProjectIdOrderByCreatedAtDesc(projectId).stream()
                .map(JobResponse::from)
                .toList();
    }
}

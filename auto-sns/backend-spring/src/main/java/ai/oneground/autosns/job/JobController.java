package ai.oneground.autosns.job;

import ai.oneground.autosns.job.dto.CreateJobRequest;
import ai.oneground.autosns.job.dto.JobResponse;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class JobController {

    private final JobService jobService;

    @PostMapping
    public ResponseEntity<JobResponse> createJob(@Valid @RequestBody CreateJobRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(jobService.createJob(request));
    }

    @GetMapping("/{id}")
    public JobResponse getJob(@PathVariable Long id) {
        return jobService.getJob(id);
    }

    @GetMapping
    public List<JobResponse> listJobs(@RequestParam Long projectId) {
        return jobService.listJobsByProject(projectId);
    }
}

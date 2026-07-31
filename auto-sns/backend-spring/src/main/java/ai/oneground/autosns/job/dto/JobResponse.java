package ai.oneground.autosns.job.dto;

import ai.oneground.autosns.domain.job.Job;
import ai.oneground.autosns.domain.job.JobStatus;
import ai.oneground.autosns.domain.job.JobType;
import java.time.Instant;

public record JobResponse(
        Long id,
        Long projectId,
        JobType type,
        JobStatus status,
        String inputJson,
        String resultJson,
        String errorMessage,
        Instant createdAt,
        Instant updatedAt) {

    public static JobResponse from(Job job) {
        return new JobResponse(
                job.getId(),
                job.getProject().getId(),
                job.getType(),
                job.getStatus(),
                job.getInputJson(),
                job.getResultJson(),
                job.getErrorMessage(),
                job.getCreatedAt(),
                job.getUpdatedAt());
    }
}

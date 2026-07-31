package ai.oneground.autosns.job.dto;

import ai.oneground.autosns.domain.job.JobType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateJobRequest(
        @NotNull Long projectId,
        @NotNull JobType type,
        @NotBlank String inputJson) {
}

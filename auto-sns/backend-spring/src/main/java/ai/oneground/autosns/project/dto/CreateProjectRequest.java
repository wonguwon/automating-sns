package ai.oneground.autosns.project.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateProjectRequest(
        @NotNull Long ownerId,
        @NotBlank String name) {
}

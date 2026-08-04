package ai.oneground.autosns.project.dto;

import ai.oneground.autosns.domain.project.Project;
import java.time.Instant;

public record ProjectResponse(
        Long id,
        Long ownerId,
        String name,
        Instant createdAt) {

    public static ProjectResponse from(Project project) {
        return new ProjectResponse(
                project.getId(),
                project.getOwner().getId(),
                project.getName(),
                project.getCreatedAt());
    }
}

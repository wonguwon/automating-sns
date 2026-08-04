package ai.oneground.autosns.project;

import ai.oneground.autosns.project.dto.CreateProjectRequest;
import ai.oneground.autosns.project.dto.ProjectResponse;
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
@RequestMapping("/api/projects")
@RequiredArgsConstructor
public class ProjectController {

    private final ProjectService projectService;

    @PostMapping
    public ResponseEntity<ProjectResponse> createProject(@Valid @RequestBody CreateProjectRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(projectService.createProject(request));
    }

    @GetMapping("/{id}")
    public ProjectResponse getProject(@PathVariable Long id) {
        return projectService.getProject(id);
    }

    @GetMapping
    public List<ProjectResponse> listProjects(@RequestParam Long ownerId) {
        return projectService.listProjectsByOwner(ownerId);
    }
}

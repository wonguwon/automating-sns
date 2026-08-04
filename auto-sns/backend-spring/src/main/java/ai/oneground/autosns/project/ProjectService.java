package ai.oneground.autosns.project;

import ai.oneground.autosns.domain.project.Project;
import ai.oneground.autosns.domain.project.ProjectRepository;
import ai.oneground.autosns.domain.user.User;
import ai.oneground.autosns.domain.user.UserRepository;
import ai.oneground.autosns.project.dto.CreateProjectRequest;
import ai.oneground.autosns.project.dto.ProjectResponse;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@RequiredArgsConstructor
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final UserRepository userRepository;

    @Transactional
    public ProjectResponse createProject(CreateProjectRequest request) {
        User owner = userRepository.findById(request.ownerId())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "사용자를 찾을 수 없습니다: " + request.ownerId()));

        Project project = Project.builder()
                .owner(owner)
                .name(request.name())
                .build();

        return ProjectResponse.from(projectRepository.save(project));
    }

    @Transactional(readOnly = true)
    public ProjectResponse getProject(Long id) {
        Project project = projectRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "프로젝트를 찾을 수 없습니다: " + id));
        return ProjectResponse.from(project);
    }

    @Transactional(readOnly = true)
    public List<ProjectResponse> listProjectsByOwner(Long ownerId) {
        return projectRepository.findByOwnerIdOrderByCreatedAtDesc(ownerId).stream()
                .map(ProjectResponse::from)
                .toList();
    }
}

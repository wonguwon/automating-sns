package ai.oneground.autosns.domain.project;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectRepository extends JpaRepository<Project, Long> {

    List<Project> findByOwnerIdOrderByCreatedAtDesc(Long ownerId);
}

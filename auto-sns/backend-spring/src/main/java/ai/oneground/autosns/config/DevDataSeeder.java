package ai.oneground.autosns.config;

import ai.oneground.autosns.domain.project.Project;
import ai.oneground.autosns.domain.project.ProjectRepository;
import ai.oneground.autosns.domain.user.User;
import ai.oneground.autosns.domain.user.UserRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * 로컬 개발 편의용 시드 데이터 — User/Project 생성 API가 아직 없어, Job API를 curl로
 * 검증하려면 최소 프로젝트 1개가 필요하다. local 프로필에서만, 테이블이 비어 있을 때만
 * 실행되며 운영 프로필에서는 로드되지 않는다.
 */
@Configuration
@Profile("local")
public class DevDataSeeder {

    @Bean
    CommandLineRunner seedDevData(UserRepository userRepository, ProjectRepository projectRepository) {
        return args -> {
            if (projectRepository.count() > 0) {
                return;
            }
            User user = userRepository.save(User.builder()
                    .email("dev@example.com")
                    .displayName("Dev User")
                    .build());
            projectRepository.save(Project.builder()
                    .owner(user)
                    .name("Dev Project")
                    .build());
        };
    }
}

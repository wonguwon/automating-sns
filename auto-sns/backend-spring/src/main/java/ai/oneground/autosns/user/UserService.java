package ai.oneground.autosns.user;

import ai.oneground.autosns.domain.user.User;
import ai.oneground.autosns.domain.user.UserRepository;
import ai.oneground.autosns.user.dto.CreateUserRequest;
import ai.oneground.autosns.user.dto.UserResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;

    @Transactional
    public UserResponse createUser(CreateUserRequest request) {
        User user = User.builder()
                .email(request.email())
                .displayName(request.displayName())
                .build();

        return UserResponse.from(userRepository.save(user));
    }

    @Transactional(readOnly = true)
    public UserResponse getUser(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "사용자를 찾을 수 없습니다: " + id));
        return UserResponse.from(user);
    }
}

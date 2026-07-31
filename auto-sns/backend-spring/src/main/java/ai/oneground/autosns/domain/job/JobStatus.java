package ai.oneground.autosns.domain.job;

/** 4단계(Python Worker)가 PENDING → RUNNING → DONE/FAILED 순서로 갱신할 예정이다. */
public enum JobStatus {
    PENDING,
    RUNNING,
    DONE,
    FAILED,
}

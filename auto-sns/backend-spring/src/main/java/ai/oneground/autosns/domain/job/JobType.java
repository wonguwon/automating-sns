package ai.oneground.autosns.domain.job;

/**
 * backend-python/ai_sns_worker/services/*.py 함수와 1:1로 대응한다(2단계에서 이관한 rss.py 포함).
 * 다른 services 파일의 실제 로직 이관이 끝나는 대로 새 타입을 추가한다.
 */
public enum JobType {
    RSS_COLLECT,
    CANDIDATE_SELECT,
    DEEP_RESEARCH,
    CARDNEWS_GENERATE,
    COVER_IMAGE_GENERATE,
    CARDNEWS_RENDER,
    REEL_SCRIPT_GENERATE,
    SCENE_IMAGE_GENERATE,
    TTS_SYNTHESIZE,
    REEL_RENDER,
}

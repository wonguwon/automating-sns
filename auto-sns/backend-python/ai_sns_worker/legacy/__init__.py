"""v3-semi-auto에서 그대로 복사해온 검증된 원본 코드.

이 패키지의 파일은 리팩토링 대상이 아니라 참고/재사용 원본이다.
services/ 계층으로 로직을 옮길 때 이 코드를 참고해 다시 작성한다.

주의: 복사 시점 기준 pipeline_common.py를 절대 경로로 import하는 부분
(`from pipeline_common import ...`)이 sources_store.py / pipeline_state.py에
남아 있어, 이 패키지를 그대로 `ai_sns_worker.legacy.x` 형태로 import하면
실패한다. services 계층 작성 시 자연히 해소될 문제라 지금은 손대지 않는다.
"""

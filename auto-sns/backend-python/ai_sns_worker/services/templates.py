"""카드뉴스 템플릿 세트(template.html + prompt.md + 예시 이미지) 관리.

템플릿 폴더명 하나가 템플릿 하나다: `TEMPLATES_DIR/<이름>/template.html`,
`TEMPLATES_DIR/<이름>/prompt.md`가 둘 다 있어야 유효한 템플릿으로 인정한다 —
이 둘은 같은 스키마의 양면(렌더 검증 ↔ 생성 규칙)이라 한쪽만 있으면 세트가 아니다.
예시 이미지(`TEMPLATES_DIR/<이름>/예시/`)는 없어도 된다.

이 관리 UI는 template.html/prompt.md를 화면에서 새로 작성해주지 않는다 — 이미 만들어둔
파일을 업로드해서 세트로 저장하는 파일 관리 기능이다(legacy와 동일한 범위, 2026-07-30
사용자 결정 — LIMITS 검증 로직이 있는 template.html을 직접 만드는 건 이 UI 범위 밖).

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 입력 DTO(dataclass)를 받고 결과 DTO(dataclass)를 반환한다.
- 실패는 st.error 대신 예외(ValueError/FileNotFoundError)로 알린다.

legacy 대응: legacy/pipeline_common.py
(list_templates, list_template_examples, is_valid_template_name, create_template,
update_template_files, add_template_examples, delete_template_example, delete_template)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from ..core.paths import TEMPLATES_DIR

TEMPLATE_EXAMPLE_DIRNAME = "예시"
TEMPLATE_EXAMPLE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


# ============================================================
# DTO
# ============================================================
@dataclass
class TemplateSummary:
    name: str
    example_count: int


@dataclass
class GetTemplateRequest:
    name: str


@dataclass
class GetTemplateResult:
    name: str
    html: str
    prompt: str
    examples: list[str] = field(default_factory=list)


@dataclass
class CreateTemplateRequest:
    name: str
    html_bytes: bytes
    prompt_bytes: bytes


@dataclass
class CreateTemplateResult:
    name: str


@dataclass
class UpdateTemplateFilesRequest:
    """None인 필드는 기존 파일을 유지한다 — services/rss.py의 UpdateFeedRequest와 동일 패턴."""

    name: str
    html_bytes: bytes | None = None
    prompt_bytes: bytes | None = None


@dataclass
class UpdateTemplateFilesResult:
    name: str


@dataclass
class AddTemplateExamplesRequest:
    name: str
    files: list[tuple[str, bytes]]


@dataclass
class AddTemplateExamplesResult:
    name: str
    saved_filenames: list[str] = field(default_factory=list)


@dataclass
class DeleteTemplateExampleRequest:
    name: str
    filename: str


@dataclass
class DeleteTemplateExampleResult:
    name: str
    deleted: bool


@dataclass
class DeleteTemplateRequest:
    name: str


@dataclass
class DeleteTemplateResult:
    name: str
    deleted: bool


# ============================================================
# 내부 헬퍼
# ============================================================
def is_valid_template_name(name: str) -> bool:
    """템플릿 폴더명으로 안전한지 검사한다 — 경로 조작 문자(/, \\, ..)와 빈 값을 막는다."""
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(c in name for c in ("/", "\\", "\0"))


def _template_dir(name: str):
    return TEMPLATES_DIR / name


def _require_template(name: str):
    template_dir = _template_dir(name)
    if not (template_dir / "template.html").exists() or not (template_dir / "prompt.md").exists():
        raise FileNotFoundError(f"템플릿을 찾을 수 없습니다: {name}")
    return template_dir


def _list_examples(template_dir) -> list[str]:
    example_dir = template_dir / TEMPLATE_EXAMPLE_DIRNAME
    if not example_dir.exists():
        return []
    return sorted(
        p.name for p in example_dir.iterdir() if p.is_file() and p.suffix.lower() in TEMPLATE_EXAMPLE_EXTS
    )


# ============================================================
# 공개 함수
# ============================================================
def list_templates() -> list[TemplateSummary]:
    """유효한(template.html+prompt.md 세트) 템플릿 목록. legacy: pipeline_common.list_templates"""
    if not TEMPLATES_DIR.exists():
        return []
    summaries = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if d.is_dir() and (d / "template.html").exists() and (d / "prompt.md").exists():
            summaries.append(TemplateSummary(name=d.name, example_count=len(_list_examples(d))))
    return summaries


def get_template(request: GetTemplateRequest) -> GetTemplateResult:
    """템플릿 내용(html/prompt/예시 파일명 목록)을 조회한다."""
    template_dir = _require_template(request.name)
    return GetTemplateResult(
        name=request.name,
        html=(template_dir / "template.html").read_text(encoding="utf-8"),
        prompt=(template_dir / "prompt.md").read_text(encoding="utf-8"),
        examples=_list_examples(template_dir),
    )


def create_template(request: CreateTemplateRequest) -> CreateTemplateResult:
    """새 템플릿 폴더를 만들고 template.html·prompt.md를 저장한다. legacy: create_template"""
    name = request.name.strip()
    if not is_valid_template_name(name):
        raise ValueError(f"템플릿 이름으로 쓸 수 없습니다: {name!r}")

    template_dir = _template_dir(name)
    if template_dir.exists():
        raise ValueError(f"이미 같은 이름의 템플릿이 있습니다: {name}")

    template_dir.mkdir(parents=True)
    (template_dir / "template.html").write_bytes(request.html_bytes)
    (template_dir / "prompt.md").write_bytes(request.prompt_bytes)
    return CreateTemplateResult(name=name)


def update_template_files(request: UpdateTemplateFilesRequest) -> UpdateTemplateFilesResult:
    """기존 템플릿의 template.html·prompt.md를 덮어쓴다 — 넘긴 것만 갱신한다.
    legacy: update_template_files"""
    template_dir = _require_template(request.name)
    if request.html_bytes is not None:
        (template_dir / "template.html").write_bytes(request.html_bytes)
    if request.prompt_bytes is not None:
        (template_dir / "prompt.md").write_bytes(request.prompt_bytes)
    return UpdateTemplateFilesResult(name=request.name)


def add_template_examples(request: AddTemplateExamplesRequest) -> AddTemplateExamplesResult:
    """예시 이미지를 템플릿의 예시/ 폴더에 저장한다. 같은 파일명이 있으면 번호를 붙여
    저장해 기존 예시를 잃지 않는다. 허용 확장자가 아닌 파일은 건너뛴다.
    legacy: add_template_examples"""
    template_dir = _require_template(request.name)
    example_dir = template_dir / TEMPLATE_EXAMPLE_DIRNAME
    example_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for filename, data in request.files:
        suffix_start = filename.rfind(".")
        suffix = filename[suffix_start:].lower() if suffix_start != -1 else ""
        if suffix not in TEMPLATE_EXAMPLE_EXTS:
            continue
        stem = filename[:suffix_start] if suffix_start != -1 else filename
        dest = example_dir / filename
        n = 1
        while dest.exists():
            dest = example_dir / f"{stem}({n}){suffix}"
            n += 1
        dest.write_bytes(data)
        saved.append(dest.name)

    return AddTemplateExamplesResult(name=request.name, saved_filenames=saved)


def delete_template_example(request: DeleteTemplateExampleRequest) -> DeleteTemplateExampleResult:
    """예시 이미지 한 장을 삭제한다. legacy: delete_template_example"""
    template_dir = _require_template(request.name)
    example_path = template_dir / TEMPLATE_EXAMPLE_DIRNAME / request.filename
    existed = example_path.exists()
    example_path.unlink(missing_ok=True)
    return DeleteTemplateExampleResult(name=request.name, deleted=existed)


def delete_template(request: DeleteTemplateRequest) -> DeleteTemplateResult:
    """템플릿 폴더 전체(template.html·prompt.md·예시/)를 삭제한다. 되돌릴 수 없다.
    legacy: delete_template"""
    template_dir = _template_dir(request.name)
    existed = template_dir.exists()
    if existed:
        shutil.rmtree(template_dir)
    return DeleteTemplateResult(name=request.name, deleted=existed)

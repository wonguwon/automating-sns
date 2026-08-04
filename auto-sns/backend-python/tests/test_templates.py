"""services/templates.py 템플릿 세트 관리 테스트."""

import pytest

from ai_sns_worker.services import templates


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """TEMPLATES_DIR을 tmp_path 아래로 바꿔 실제 storage/templates/를 건드리지 않는다."""
    monkeypatch.setattr(templates, "TEMPLATES_DIR", tmp_path / "templates")


def test_list_templates_empty_when_dir_missing():
    assert templates.list_templates() == []


def test_create_then_list_and_get_template():
    result = templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"<html></html>", prompt_bytes=b"# prompt")
    )
    assert result.name == "기본"

    summaries = templates.list_templates()
    assert len(summaries) == 1
    assert summaries[0].name == "기본"
    assert summaries[0].example_count == 0

    fetched = templates.get_template(templates.GetTemplateRequest(name="기본"))
    assert fetched.html == "<html></html>"
    assert fetched.prompt == "# prompt"
    assert fetched.examples == []


def test_create_template_invalid_name_raises():
    with pytest.raises(ValueError):
        templates.create_template(
            templates.CreateTemplateRequest(name="../escape", html_bytes=b"", prompt_bytes=b"")
        )


def test_create_template_duplicate_raises():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"a", prompt_bytes=b"b")
    )
    with pytest.raises(ValueError):
        templates.create_template(
            templates.CreateTemplateRequest(name="기본", html_bytes=b"a", prompt_bytes=b"b")
        )


def test_get_missing_template_raises():
    with pytest.raises(FileNotFoundError):
        templates.get_template(templates.GetTemplateRequest(name="없음"))


def test_update_template_files_partial():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"old-html", prompt_bytes=b"old-prompt")
    )
    templates.update_template_files(
        templates.UpdateTemplateFilesRequest(name="기본", html_bytes=b"new-html")
    )
    fetched = templates.get_template(templates.GetTemplateRequest(name="기본"))
    assert fetched.html == "new-html"
    assert fetched.prompt == "old-prompt"


def test_add_template_examples_filters_extension_and_dedupes_name():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"a", prompt_bytes=b"b")
    )
    result = templates.add_template_examples(
        templates.AddTemplateExamplesRequest(
            name="기본",
            files=[("a.png", b"1"), ("a.png", b"2"), ("skip.txt", b"3")],
        )
    )
    assert result.saved_filenames == ["a.png", "a(1).png"]
    fetched = templates.get_template(templates.GetTemplateRequest(name="기본"))
    assert fetched.examples == ["a(1).png", "a.png"]


def test_delete_template_example():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"a", prompt_bytes=b"b")
    )
    templates.add_template_examples(
        templates.AddTemplateExamplesRequest(name="기본", files=[("a.png", b"1")])
    )
    deleted = templates.delete_template_example(
        templates.DeleteTemplateExampleRequest(name="기본", filename="a.png")
    )
    assert deleted.deleted is True
    assert templates.get_template(templates.GetTemplateRequest(name="기본")).examples == []

    again = templates.delete_template_example(
        templates.DeleteTemplateExampleRequest(name="기본", filename="a.png")
    )
    assert again.deleted is False


def test_delete_template_removes_whole_set():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"a", prompt_bytes=b"b")
    )
    result = templates.delete_template(templates.DeleteTemplateRequest(name="기본"))
    assert result.deleted is True
    assert templates.list_templates() == []

    again = templates.delete_template(templates.DeleteTemplateRequest(name="기본"))
    assert again.deleted is False

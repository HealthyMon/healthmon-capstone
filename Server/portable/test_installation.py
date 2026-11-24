from pathlib import Path
from dotenv import dotenv_values

from Server.scripts import manage


def test_separate_installations_with_same_directory_name_do_not_share_database(tmp_path, monkeypatch):
    projects = []
    for parent in ('first', 'second'):
        root = tmp_path / parent / 'app'
        root.mkdir(parents=True)
        monkeypatch.setattr(manage, 'ROOT', root)
        manage.initialize(test=True, port=18092)
        values = dotenv_values(root / '.env')
        projects.append(values['COMPOSE_PROJECT_NAME'])
    assert projects[0] != projects[1]
    assert all(project.startswith('app-') for project in projects)


def test_reinstall_preserves_project_credentials_and_database_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, 'ROOT', tmp_path)
    manage.initialize(test=True, port=18092)
    original = (tmp_path / '.env').read_bytes()
    manage.initialize(test=True, port=8020)
    assert (tmp_path / '.env').read_bytes() == original

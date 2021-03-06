import pytest
import os.path
import requests
import json
from click.testing import CliRunner
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from tokens import InvalidCredentialsError

from lizzy_client.cli import main, fetch_token
from lizzy_client.version import VERSION, MAJOR_VERSION, MINOR_VERSION, REVISION

test_dir = os.path.dirname(__file__)
config_path = os.path.join(test_dir, 'test_config.yaml')

FAKE_ENV = {'OAUTH2_ACCESS_TOKEN_URL': 'oauth.example.com',
            'LIZZY_URL': 'lizzy.example.com'}


class FakeLizzy:
    final_state = 'CF:CREATE_COMPLETE'
    raise_exception = False

    def __init__(self, base_url: str, access_token: str):
        ...

    @classmethod
    def reset(cls):
        cls.final_state = 'CF:CREATE_COMPLETE'
        cls.raise_exception = False

    def delete(self, stack_id):
        ...

    def new_stack(self, image_version, keep_stacks, traffic, definition, app_version, parameters):
        assert isinstance(traffic, int)
        if self.raise_exception:
            raise requests.HTTPError('404 Not Found')
        else:
            return '57ACC1D'

    def traffic(self, stack_id, percentage):
        ...

    def wait_for_deployment(self, stack_id: str) -> [str]:
        return ['CF:WAITING', self.final_state]

    def get_stacks(self) -> list:
        stack1 = {'stack_name': 'stack1',
                  'stack_version': '42',
                  'image_version': 'd42',
                  'status': 'CF:CREATE_COMPLETE',
                  'creation_time': '2016-01-01T12:00:00Z'}

        stack2 = {'stack_name': 'stack2',
                  'stack_version': '42',
                  'image_version': 'd42',
                  'status': 'CF:TEST',
                  'creation_time': '2015-12-01T12:00:00Z'}

        stack3 = {'stack_name': 'stack2',
                  'stack_version': '42',
                  'image_version': 'd42',
                  'status': 'LIZZY:REMOVED',
                  'creation_time': '2015-12-01T12:00:00Z'}
        if self.raise_exception:
            raise requests.HTTPError('404 Not Found')
        else:
            return [stack1, stack2, stack3]


@pytest.fixture
def mock_get_token(monkeypatch):
    mock = MagicMock()
    mock.return_value = '4CC3557OCC3N'
    monkeypatch.setattr('lizzy_client.cli.get_token', mock)
    return mock


@pytest.fixture
def mock_fake_lizzy(monkeypatch):
    FakeLizzy.reset()
    monkeypatch.setattr('lizzy_client.cli.Lizzy', FakeLizzy)
    return FakeLizzy


def test_fetch_token(mock_get_token):
    token = fetch_token('https://example.com', ['scope'], credentials_dir='/meta/credentials')

    assert token == '4CC3557OCC3N'

    mock_get_token.side_effect = InvalidCredentialsError('Error')

    with pytest.raises(SystemExit) as exc_info:  # type: py.code.ExceptionInfo
        fetch_token('https://example.com', ['scope'], credentials_dir='/meta/credentials')

    exception = exc_info.value
    assert repr(exception) == 'SystemExit(1,)'


def test_create(mock_get_token, mock_fake_lizzy):
    runner = CliRunner()
    result = runner.invoke(main, ['create', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Fetching authentication token.. . OK' in result.output
    assert 'Requesting new stack.. OK' in result.output
    assert 'Stack ID: 57ACC1D' in result.output
    assert 'Waiting for new stack... . . OK' in result.output
    assert 'Deployment Successful' in result.output

    result = runner.invoke(main, ['create', '-v', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Fetching authentication token.. . OK' in result.output
    assert 'Requesting new stack.. OK' in result.output
    assert 'Stack ID: 57ACC1D' in result.output
    assert 'Waiting for new stack...\n' in result.output
    assert 'CF:WAITING' in result.output
    assert 'CF:CREATE_COMPLETE' in result.output
    assert 'Deployment Successful' in result.output

    FakeLizzy.final_state = 'CF:ROLLBACK_COMPLETE'
    result = runner.invoke(main, ['create', '-v', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Stack was rollback after deployment. Check you application log for possible reasons.' in result.output

    FakeLizzy.final_state = 'LIZZY:REMOVED'
    result = runner.invoke(main, ['create', '-v', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Stack was removed before deployment finished.' in result.output

    FakeLizzy.final_state = 'CF:CREATE_FAILED'
    result = runner.invoke(main, ['create', '-v', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Deployment failed: CF:CREATE_FAILED' in result.output

    FakeLizzy.reset()
    FakeLizzy.raise_exception = True
    result = runner.invoke(main, ['create', '-v', config_path, '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Deployment failed: 404 Not Found' in result.output


def test_delete(mock_get_token, mock_fake_lizzy):
    runner = CliRunner()
    result = runner.invoke(main, ['delete', 'lizzy-test', '1.0'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Requesting stack deletion.. OK' in result.output


def test_traffic(mock_get_token, mock_fake_lizzy):
    runner = CliRunner()
    result = runner.invoke(main, ['traffic', 'lizzy-test', '1.0', '90'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Requesting traffic change.. OK' in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ['version'], env=FAKE_ENV, catch_exceptions=False)
    for version_segment in (VERSION, MAJOR_VERSION, MINOR_VERSION, REVISION):
        assert str(version_segment) in result.output


def test_list(mock_get_token, mock_fake_lizzy):
    stack1 = {'stack_name': 'stack1',
              'version': '42',
              'image_version': 'd42',
              'status': 'CF:CREATE_COMPLETE',
              'creation_time': 1451649600.0}

    stack2 = {'stack_name': 'stack2',
              'version': '42',
              'image_version': 'd42',
              'status': 'CF:TEST',
              'creation_time': 1448971200.0}

    stack3 = {'stack_name': 'stack2',
              'version': '42',
              'image_version': 'd42',
              'status': 'LIZZY:REMOVED',
              'creation_time': 1448971200.0}

    runner = CliRunner()
    regular_list_result = runner.invoke(main, ['list', '-o', 'json'], env=FAKE_ENV, catch_exceptions=False)
    str_json = regular_list_result.output.splitlines()[-1]  # type: str
    regular_list = json.loads(str_json)  # type: list
    assert regular_list == [stack1, stack2]

    runner = CliRunner()
    all_list_result = runner.invoke(main, ['list', '--all', '-o', 'json'], env=FAKE_ENV, catch_exceptions=False)
    str_json = all_list_result.output.splitlines()[-1]  # type: str
    all_list = json.loads(str_json)  # type: list
    assert all_list == [stack1, stack2, stack3]

    runner = CliRunner()
    stack1_list_result = runner.invoke(main, ['list', '--all', '-o', 'json', 'stack1'], env=FAKE_ENV,
                                       catch_exceptions=False)
    str_json = stack1_list_result.output.splitlines()[-1]  # type: str
    stack1_list = json.loads(str_json)  # type: list
    assert stack1_list == [stack1]

    FakeLizzy.raise_exception = True
    result = runner.invoke(main, ['list', '-o', 'json'], env=FAKE_ENV, catch_exceptions=False)
    assert 'Failed to get stacks: 404 Not Found' in result.output

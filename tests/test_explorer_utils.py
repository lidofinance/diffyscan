import os
from diffyscan.utils.explorer import get_explorer_hostname


def test_get_explorer_hostname_env(monkeypatch):
    monkeypatch.setenv('MYHOST', 'example.com')
    cfg = {'explorer_hostname_env_var': 'MYHOST'}
    assert get_explorer_hostname(cfg) == 'example.com'


def test_get_explorer_hostname_direct():
    cfg = {'explorer_hostname': 'api.etherscan.io'}
    assert get_explorer_hostname(cfg) == 'api.etherscan.io'

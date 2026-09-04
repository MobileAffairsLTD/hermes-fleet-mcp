from hermes_fleet_mcp.server import LOCALHOST_HOSTS, _transport_security


def test_default_disables_dns_rebinding_protection():
    ts = _transport_security(None)
    assert ts.enable_dns_rebinding_protection is False


def test_empty_list_disables_dns_rebinding_protection():
    ts = _transport_security([])
    assert ts.enable_dns_rebinding_protection is False


def test_allowed_hosts_enable_protection_with_whitelist():
    ts = _transport_security(["dmsdevteam1.ngrok.app"])
    assert ts.enable_dns_rebinding_protection is True
    assert "dmsdevteam1.ngrok.app" in ts.allowed_hosts
    # bare host auto-expands to also allow any port (Host header carries the port)
    assert "dmsdevteam1.ngrok.app:*" in ts.allowed_hosts
    # localhost defaults are preserved so local dev still works
    for h in LOCALHOST_HOSTS:
        assert h in ts.allowed_hosts

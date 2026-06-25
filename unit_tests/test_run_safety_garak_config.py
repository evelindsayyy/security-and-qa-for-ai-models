"""Garak probe override flag is parsed by safety.run."""

from safety.run import parse_args


def test_garak_probes_flag_parsed() -> None:
    _sub, cfg = parse_args(["--garak-probes", "encoding,promptinject", "GPT 4.1 Mini"])
    assert cfg.garak_probes == "encoding,promptinject"


def test_skip_garak_flag_parsed() -> None:
    _sub, cfg = parse_args(["--skip-garak"])
    assert cfg.skip_garak is True

"""Unit tests for SignalPathEngine."""

from pathlib import Path

from core.diagnostics.signal_path_engine import SignalPathEngine


def test_signal_path_plan_requires_citations(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    graph = {
        "domain": "radar",
        "version": "1.0",
        "signal_paths": [
            {
                "id": "tx_chain",
                "name": "Transmitter chain",
                "keywords": ["transmitter"],
                "nodes": [
                    {
                        "id": "power_supply",
                        "name": "Power supply",
                        "check": "Verify input voltage.",
                        "keywords": ["power supply", "voltage"],
                    },
                    {
                        "id": "exciter",
                        "name": "Exciter",
                        "check": "Confirm exciter output.",
                        "keywords": ["exciter", "drive level"],
                    },
                ],
            }
        ],
    }
    (graph_dir / "radar.json").write_text(
        __import__("json").dumps(graph), encoding="utf-8"
    )

    engine = SignalPathEngine(graph_dir=graph_dir)
    result = engine.build_plan(
        question="transmitter output weak",
        context_docs=[],
        domain_hint="radar",
    )

    assert result["status"] == "refusal"
    assert result["reason"] == "missing_citations"


def test_signal_path_plan_with_citations(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    graph = {
        "domain": "radar",
        "version": "1.0",
        "signal_paths": [
            {
                "id": "tx_chain",
                "name": "Transmitter chain",
                "keywords": ["transmitter"],
                "nodes": [
                    {
                        "id": "power_supply",
                        "name": "Power supply",
                        "check": "Verify input voltage.",
                        "keywords": ["power supply", "voltage"],
                    },
                    {
                        "id": "exciter",
                        "name": "Exciter",
                        "check": "Confirm exciter output.",
                        "keywords": ["exciter", "drive level"],
                    },
                    {
                        "id": "transmitter",
                        "name": "Transmitter",
                        "check": "Measure transmitter output.",
                        "keywords": ["transmitter", "output power"],
                    },
                ],
            }
        ],
    }
    (graph_dir / "radar.json").write_text(
        __import__("json").dumps(graph), encoding="utf-8"
    )

    context_docs = [
        {
            "source": "radar_manual.pdf",
            "page": 10,
            "snippet": "Power supply voltage checks for transmitter chain.",
            "text": "Power supply voltage checks for transmitter chain.",
            "domain": "radar",
        },
        {
            "source": "radar_manual.pdf",
            "page": 12,
            "snippet": "Exciter drive level verification.",
            "text": "Exciter drive level verification.",
            "domain": "radar",
        },
        {
            "source": "radar_manual.pdf",
            "page": 15,
            "snippet": "Transmitter output power measurement.",
            "text": "Transmitter output power measurement.",
            "domain": "radar",
        },
    ]

    engine = SignalPathEngine(graph_dir=graph_dir)
    result = engine.build_plan(
        question="transmitter output weak",
        context_docs=context_docs,
        domain_hint="radar",
    )

    assert result["status"] == "success"
    assert "Branching diagnostic plan" in result.get("plan", "")

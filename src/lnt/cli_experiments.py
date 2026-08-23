"""Russian CLI contracts for experiments and hypotheses."""
# ruff: noqa: A002, T201, TC003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from lnt.cli_research import read_payload, run_check, run_confirm, run_trends, validation_fields
from lnt.errors import InputError
from lnt.experiments import Experiment, ExperimentStore
from lnt.research import Hypothesis, HypothesisStore, hypothesis_status_label
from lnt.statistics import AnalysisContext, PairedUnit, estimate_paired


class ParserFactory(Protocol):
    """Capability used by argparse subparser registration."""

    def __call__(self, name: str, *, help: str) -> argparse.ArgumentParser:
        """Create a named parser with localized help."""
        ...


def configure_research_parsers(add_parser: ParserFactory) -> None:
    """Register experiment and hypothesis command trees."""
    experiment = add_parser("experiment", help="эксперименты и расчёты")
    commands = experiment.add_subparsers(dest="experiment_command", required=True)
    for name in ("create", "show"):
        command = commands.add_parser(name)
        command.add_argument("value")
        _root(command)
        command.set_defaults(handler=_experiment)
    listing = commands.add_parser("list")
    _root(listing)
    listing.set_defaults(handler=_experiment)
    stats = commands.add_parser("stats")
    stats.add_argument("value")
    stats.add_argument("--estimand", required=True)
    stats.add_argument("--units", required=True)
    stats.add_argument("--pair", action="append", default=[])
    _root(stats)
    stats.set_defaults(handler=_experiment)
    trends = commands.add_parser("trends")
    trends.add_argument("value", help="путь к JSON-файлу параметров тренда")
    _root(trends)
    trends.set_defaults(handler=_experiment)
    check = commands.add_parser("check")
    check.add_argument("value", help="идентификатор эксперимента")
    _root(check)
    check.set_defaults(handler=_experiment)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("value", help="идентификатор запуска протокола")
    confirm.add_argument("--actor", required=True, help="имя подтверждающего оператора")
    _root(confirm)
    confirm.set_defaults(handler=_experiment)
    hypothesis = add_parser("hypothesis", help="аудитируемые гипотезы")
    hypotheses = hypothesis.add_subparsers(dest="hypothesis_command", required=True)
    for name in ("add", "edit", "status"):
        command = hypotheses.add_parser(name)
        value_help = (
            "путь к JSON-файлу гипотезы" if name in {"add", "edit"} else "идентификатор гипотезы"
        )
        command.add_argument("value", help=value_help)
        _root(command)
        command.set_defaults(handler=_hypothesis)


def _root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path.home() / "lnt-sessions")


def _experiment(args: argparse.Namespace) -> int:
    store = ExperimentStore(args.root)
    match args.experiment_command:
        case "create":
            experiment = _experiment_file(Path(args.value))
            store.save(experiment, expected_revision=0)
            print(f"Эксперимент создан: {experiment.experiment_id}")
        case "list":
            ids = sorted(path.name for path in store.root.iterdir()) if store.root.is_dir() else []
            print("\n".join(ids) if ids else "Экспериментов нет")
        case "show":
            print(store.load(args.value).model_dump_json(indent=2))
        case "stats":
            experiment = store.load(args.value)
            pairs = tuple(_pair(raw) for raw in args.pair)
            result = estimate_paired(
                pairs,
                AnalysisContext(
                    protocol=experiment.protocol,
                    hierarchy=(experiment.protocol.site_key, experiment.protocol.subject_key),
                    missing_count=0,
                ),
            )
            payload = asdict(result)
            payload["metadata"] = {
                "units": args.units,
                "estimator": result.metadata.estimator_name,
                "n": result.metadata.n,
                "provenance": {
                    "experiment_id": experiment.experiment_id,
                    "revision": experiment.revision,
                    "estimand": args.estimand,
                },
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        case "trends":
            return run_trends(Path(args.value))
        case "check":
            return run_check(args.value, args.root)
        case "confirm":
            return run_confirm(args.value, args.actor, args.root)
        case _:
            raise InputError("неизвестная команда experiment")
    return 0


def _hypothesis(args: argparse.Namespace) -> int:
    store = HypothesisStore(args.root)
    match args.hypothesis_command:
        case "add" | "edit":
            hypothesis = _hypothesis_file(Path(args.value))
            expected = 0 if args.hypothesis_command == "add" else hypothesis.revision - 1
            store.save(hypothesis, expected_revision=expected)
            print(f"Гипотеза сохранена: {hypothesis.hypothesis_id}")
        case "status":
            hypothesis = store.load(args.value)
            print(f"{hypothesis.hypothesis_id}: {hypothesis_status_label(hypothesis.status)}")
        case _:
            raise InputError("неизвестная команда hypothesis")
    return 0


def _experiment_file(path: Path) -> Experiment:
    try:
        return Experiment.model_validate_json(read_payload(path))
    except (OSError, ValidationError) as error:
        raise InputError(f"эксперимент: некорректный файл {path}") from error


def _hypothesis_file(path: Path) -> Hypothesis:
    try:
        return Hypothesis.model_validate_json(read_payload(path))
    except OSError as error:
        raise InputError(f"гипотеза: не удалось прочитать файл {path}: {error}") from error
    except ValidationError as error:
        raise InputError(
            f"гипотеза: некорректные поля {path}: {validation_fields(error)}"
        ) from error


def _pair(raw: str) -> PairedUnit:
    try:
        unit_id, value_a, value_b = raw.split(":", maxsplit=2)
        return PairedUnit(
            unit_id_a=unit_id,
            unit_id_b=unit_id,
            value_a=float(value_a),
            value_b=float(value_b),
        )
    except ValueError as error:
        raise InputError("пара должна иметь формат unit:a:b") from error

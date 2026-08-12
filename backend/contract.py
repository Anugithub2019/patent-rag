"""Parsing and validation for the shared PatentRAG API contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse
from uuid import UUID

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contracts" / "api-contract.schema.json"
with CONTRACT_PATH.open(encoding="utf-8") as contract_file:
    CONTRACT = json.load(contract_file)


class ContractError(ValueError):
    """Raised when upstream or internal data violates the public contract."""


def validate_contract(value: Any, definition: str) -> None:
    """Validate public boundary objects without requiring a runtime dependency."""
    if definition == "analysisV2":
        _validate_analysis_shape(value)
    elif definition == "queryRequest":
        _require_record(value, "queryRequest")
        _exact_keys(value, {"text"}, "queryRequest")
        _require_text(value.get("text"), "queryRequest.text")
    elif definition == "queryAccepted":
        _require_record(value, "queryAccepted")
        _exact_keys(value, {"job_id"}, "queryAccepted")
        try:
            UUID(value.get("job_id", ""))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ContractError("queryAccepted.job_id must be a UUID") from exc
    elif definition == "jobResult":
        _require_record(value, "jobResult")
        status = value.get("status")
        if status == "pending":
            _exact_keys(value, {"status"}, "jobResult")
        elif status == "complete":
            _exact_keys(value, {"status", "data"}, "jobResult")
            validate_analysis(value.get("data"))
        elif status == "failed":
            required = {"status", "error"}
            allowed = required | {"debug"}
            if missing := required - value.keys():
                raise ContractError(f"jobResult is missing {sorted(missing)[0]}")
            if extra := value.keys() - allowed:
                raise ContractError(f"jobResult.{sorted(extra)[0]} is not allowed")
            _require_text(value.get("error"), "jobResult.error")
            if "debug" in value:
                debug = value["debug"]
                _require_record(debug, "jobResult.debug")
                _exact_keys(debug, {"validation_error", "upstream_response"}, "jobResult.debug")
                _require_text(debug["validation_error"], "jobResult.debug.validation_error")
        else:
            raise ContractError("jobResult.status is unsupported")
    else:
        raise ContractError(f"unknown contract definition: {definition}")


def _require_record(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")


def _require_text(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be non-empty text")


def _require_positive_integer(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{path} must be a positive integer")


def _exact_keys(value: Dict[str, Any], keys: set[str], path: str) -> None:
    missing = keys - value.keys()
    extra = value.keys() - keys
    if missing:
        raise ContractError(f"{path} is missing {sorted(missing)[0]}")
    if extra:
        raise ContractError(f"{path}.{sorted(extra)[0]} is not allowed")


def _validate_analysis_shape(analysis: Any) -> None:
    _require_record(analysis, "analysisV2")
    _exact_keys(analysis, {"schema_version", "overall_assessment", "features"}, "analysisV2")
    if analysis["schema_version"] != 2:
        raise ContractError("schema_version must be 2")
    assessment = analysis["overall_assessment"]
    _require_record(assessment, "overall_assessment")
    _exact_keys(assessment, {"status", "summary"}, "overall_assessment")
    if assessment["status"] not in {"no_single_reference_match", "potentially_anticipated", "inconclusive"}:
        raise ContractError("overall_assessment.status is unsupported")
    _require_text(assessment["summary"], "overall_assessment.summary")
    features = analysis["features"]
    if not isinstance(features, list) or not features:
        raise ContractError("features must be a non-empty array")
    for feature_index, feature in enumerate(features):
        path = f"features[{feature_index}]"
        _require_record(feature, path)
        _exact_keys(feature, {"feature_id", "feature_text", "matches"}, path)
        _require_positive_integer(feature["feature_id"], f"{path}.feature_id")
        _require_text(feature["feature_text"], f"{path}.feature_text")
        if not isinstance(feature["matches"], list):
            raise ContractError(f"{path}.matches must be an array")
        for match_index, match in enumerate(feature["matches"]):
            match_path = f"{path}.matches[{match_index}]"
            _require_record(match, match_path)
            required = {"reference_id", "patent_id", "title", "status", "disclosure_summary", "evidence"}
            allowed = required | {"source_url"}
            if missing := required - match.keys():
                raise ContractError(f"{match_path} is missing {sorted(missing)[0]}")
            if extra := match.keys() - allowed:
                raise ContractError(f"{match_path}.{sorted(extra)[0]} is not allowed")
            for key in ("reference_id", "patent_id", "title", "disclosure_summary"):
                _require_text(match[key], f"{match_path}.{key}")
            if match["status"] not in {"disclosed", "partially_disclosed"}:
                raise ContractError(f"{match_path}.status is unsupported")
            if not isinstance(match["evidence"], list):
                raise ContractError(f"{match_path}.evidence must be an array")
            for evidence_index, evidence in enumerate(match["evidence"]):
                evidence_path = f"{match_path}.evidence[{evidence_index}]"
                _require_record(evidence, evidence_path)
                required_evidence = {"passage"}
                if not required_evidence <= evidence.keys() or not evidence.keys() <= {"passage", "location"}:
                    raise ContractError(f"{evidence_path} has invalid fields")
                _require_text(evidence["passage"], f"{evidence_path}.passage")
                if "location" in evidence:
                    _require_text(evidence["location"], f"{evidence_path}.location")
            if "source_url" in match:
                _require_text(match["source_url"], f"{match_path}.source_url")
                parsed = urlparse(match["source_url"])
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ContractError(f"{match_path}.source_url must be an http(s) URL")


def _validate_semantics(analysis: Dict[str, Any]) -> None:
    feature_ids = set()
    reference_metadata = {}
    for feature in analysis["features"]:
        feature_id = feature["feature_id"]
        if feature_id in feature_ids:
            raise ContractError(f"duplicate feature_id: {feature_id}")
        feature_ids.add(feature_id)

        reference_ids = set()
        for match in feature["matches"]:
            reference_id = match["reference_id"]
            if reference_id in reference_ids:
                raise ContractError(f"duplicate reference_id {reference_id} in feature {feature_id}")
            reference_ids.add(reference_id)
            metadata = (match["patent_id"], match["title"])
            if reference_id in reference_metadata and reference_metadata[reference_id] != metadata:
                raise ContractError(f"conflicting metadata for reference_id: {reference_id}")
            reference_metadata[reference_id] = metadata


def validate_analysis(analysis: Any) -> Dict[str, Any]:
    _validate_analysis_shape(analysis)
    _validate_semantics(analysis)
    return analysis


def _unavailable(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_analysis_candidate(candidate: Any) -> Any:
    """Repair known nullable LLM output without weakening the public contract."""
    if not isinstance(candidate, dict):
        return candidate

    normalized = deepcopy(candidate)
    features = normalized.get("features")
    if not isinstance(features, list):
        return normalized

    required_match_fields = {
        "reference_id",
        "patent_id",
        "title",
        "status",
        "disclosure_summary",
        "evidence",
    }

    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("matches"), list):
            continue

        matches = []
        for match in feature["matches"]:
            if not isinstance(match, dict):
                matches.append(match)
                continue
            if any(key not in match or _unavailable(match[key]) for key in required_match_fields):
                continue

            if _unavailable(match.get("source_url")):
                match.pop("source_url", None)
            if isinstance(match.get("evidence"), list):
                evidence_items = []
                for evidence in match["evidence"]:
                    if not isinstance(evidence, dict):
                        evidence_items.append(evidence)
                        continue
                    if "passage" not in evidence or _unavailable(evidence["passage"]):
                        continue
                    if _unavailable(evidence.get("location")):
                        evidence.pop("location", None)
                    evidence_items.append(evidence)
                match["evidence"] = evidence_items
            matches.append(match)
        feature["matches"] = matches

    return normalized


def parse_analysis_response(response_data: Any) -> Dict[str, Any]:
    """Extract Schema v2 JSON from the Hashtag response and validate it."""
    if not isinstance(response_data, dict):
        raise ContractError("upstream response must be an object")

    candidate = response_data if response_data.get("schema_version") == 2 else response_data.get("answer")
    if isinstance(candidate, str):
        text = candidate.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in ("```", "```json"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContractError("upstream answer is not valid Schema v2 JSON") from exc

    return validate_analysis(_normalize_analysis_candidate(candidate))


def make_job_result(
    status: str,
    *,
    data: Any = None,
    error: str | None = None,
    debug: Any = None,
) -> Dict[str, Any]:
    if status == "pending":
        result = {"status": "pending"}
    elif status == "complete":
        result = {"status": "complete", "data": validate_analysis(data)}
    elif status == "failed":
        result = {"status": "failed", "error": str(error or "Query processing failed")}
        if debug is not None:
            result["debug"] = debug
    else:
        raise ContractError(f"unsupported job status: {status}")
    validate_contract(result, "jobResult")
    return result

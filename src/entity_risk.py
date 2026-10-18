"""Independent entity evidence and bounded, temporal corporate relationships.

The operator registry is never accepted from a Pix payload. Propagated assessments
are not written as new own-account evidence. Missing registry means unknown links.
"""

import copy
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from src.financial_features import directional_contacts, financial_features
from src.risk.scoring import rule_evidence, score_decision, summarize_factor, summarize_score
from src.risk.types import RuleMatch

Document = Annotated[str, Field(pattern=r"^(?:[0-9]{11}|[0-9]{14})$")]
ROLE_STRENGTH = {
    "controller": 1.0,
    "beneficial_owner": 1.0,
    "administrator": 0.5,
    "minority_partner": 0.2,
    "accountant": 0.0,
}
MAX_GRAPH_POINTS = 20  # Verified entity relationships remain one capped factor.


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CorporateLink(RegistryModel):
    link_id: str = Field(min_length=1, max_length=128)
    person_or_company: Document
    company: Annotated[str, Field(pattern=r"^[0-9]{14}$")]
    role: Literal["controller", "beneficial_owner", "administrator", "minority_partner", "accountant"]
    verified: bool = Field(strict=True)
    valid_from: AwareDatetime
    valid_until: AwareDatetime | None = None
    known_at: AwareDatetime
    reference: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_period(self):
        if self.person_or_company == self.company:
            raise ValueError("A corporate link cannot point to itself")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self

    def active(self, at):
        return self.valid_from <= at and (self.valid_until is None or at < self.valid_until)


class ConfirmedIncident(RegistryModel):
    incident_id: str = Field(min_length=1, max_length=128)
    documents: tuple[Document, ...] = Field(min_length=1)
    severity: int = Field(strict=True, ge=1, le=100)
    occurred_at: AwareDatetime
    known_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    revoked_at: AwareDatetime | None = None
    reference: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_incident(self):
        if self.known_at < self.occurred_at:
            raise ValueError("An incident cannot be known before it occurs")
        if self.expires_at is not None and self.expires_at <= self.occurred_at:
            raise ValueError("expires_at must follow occurred_at")
        if self.revoked_at is not None and self.revoked_at < self.known_at:
            raise ValueError("revoked_at cannot precede known_at")
        if len(set(self.documents)) != len(self.documents):
            raise ValueError("Duplicate documents in one incident")
        return self

    def available(self, at):
        return (
            self.known_at <= at
            and self.occurred_at <= at
            and (self.expires_at is None or at < self.expires_at)
            and (self.revoked_at is None or at < self.revoked_at)
        )


class EntityRegistry(RegistryModel):
    version: str = Field(min_length=1, max_length=128)
    links: tuple[CorporateLink, ...] = Field(default=(), max_length=5000)
    incidents: tuple[ConfirmedIncident, ...] = Field(default=(), max_length=5000)

    @model_validator(mode="after")
    def unique_references(self):
        if len({link.link_id for link in self.links}) != len(self.links):
            raise ValueError("Duplicate link_id")
        if len({event.incident_id for event in self.incidents}) != len(self.incidents):
            raise ValueError("One incident_id must list all affected documents in one record")
        return self


@dataclass(frozen=True)
class OwnEvidence:
    event_id: str
    document: str
    received_at: datetime
    increment: int
    account_identity: str | None = None


class EntityRiskService:
    def __init__(self, mode="shadow", registry_path=None, *, registry=None):
        if mode not in {"off", "shadow", "contribute"}:
            raise ValueError("ENTITY_RISK_MODE must be off, shadow or contribute")
        self.mode = mode
        if registry_path is not None and registry is not None:
            raise ValueError("Use a registry path or an in-memory registry")
        self.registry_hash = None
        self.registry = registry
        if registry_path is not None:
            raw = Path(registry_path).read_bytes()
            self.registry = EntityRegistry.model_validate_json(raw)
            self.registry_hash = hashlib.sha256(raw).hexdigest()
        elif registry is not None:
            self.registry_hash = hashlib.sha256(registry.model_dump_json().encode()).hexdigest()

    @property
    def enabled(self):
        return self.mode != "off"

    def paths(self, document, at, *, occurred_at=None):
        """At most 3 corporate edges/100 entities; weak roles cannot bridge companies.

        Current owners identify the source company's context even for a new CNPJ.
        Downstream ownership of an incident's company must also exist at the
        incident. Ended memberships are not inferred from the current registry.
        """
        adjacency = defaultdict(list)
        for link in self.registry.links if self.registry else ():
            strength = ROLE_STRENGTH[link.role]
            if link.verified and strength > 0 and link.known_at <= at and link.active(at):
                active_then = occurred_at is None or link.active(occurred_at)
                adjacency[link.person_or_company].append(
                    (link.company, strength, link.link_id, False, active_then)
                )
                adjacency[link.company].append(
                    (link.person_or_company, strength, link.link_id, True, active_then)
                )
        best, frontier, truncated = {document: (1.0, ())}, [(document, 1.0, (), False)], False
        best_states = {(document, False): 1.0}
        for _ in range(3):
            next_frontier = []
            for node, strength, path, descending in frontier:
                for neighbor, edge_strength, link_id, upstream, active_then in sorted(adjacency[node]):
                    if link_id in path or neighbor == document:
                        continue
                    # Weak roles can be inspected directly, not used as bridges.
                    if path and (edge_strength < 0.75 or strength < 0.75):
                        continue
                    next_descending = descending or not upstream
                    if next_descending and not active_then:
                        continue
                    weight = strength * edge_strength
                    if neighbor not in best and len(best) >= 100:
                        truncated = True
                        continue
                    state = (neighbor, next_descending)
                    if best_states.get(state, 0) >= weight:
                        continue
                    best_states[state] = weight
                    if neighbor not in best or best[neighbor][0] < weight:
                        best[neighbor] = (weight, (*path, link_id))
                    if weight >= 0.75:
                        next_frontier.append((neighbor, weight, (*path, link_id), next_descending))
            frontier = next_frontier
        return best, truncated

    def documents(self, document, at, payments=()):
        contacts = directional_contacts(document, at, payments)
        return sorted(
            set(self.paths(document, at)[0]) | set(contacts["incoming"]) | set(contacts["outgoing"])
        )

    def assess(
        self,
        document,
        at,
        evidence,
        *,
        current_increment=0,
        current_event_id="current",
        current_account_identity=None,
        own_window_hours=24,
        own_threshold=40,
        history_truncated=False,
        payments=(),
        payments_truncated=False,
    ):
        result = {
            "mode": self.mode,
            "status": "disabled" if not self.enabled else "assessed",
            "score_semantics": "heuristic_not_probability_or_confirmed_fraud",
            "registry_status": "loaded" if self.registry is not None else "not_configured",
            "registry_version": self.registry.version if self.registry else None,
            "registry_sha256": self.registry_hash,
            "own_entity": {
                "score": None,
                "risk_events": 0,
                "accounts_with_evidence": 0,
                "window_hours": own_window_hours,
                "history_status": "not_queried",
            },
            "relationships": {
                "exposure_score": 0,
                "confirmed_incidents": 0,
                "strong_confirmed_incidents": 0,
                "own_confirmed_incidents": 0,
                "related_entities": 0,
                "related_company_roots_with_evidence": 0,
                "max_related_untrust": 0,
                "top_related_untrust": [],
                "evidence": [],
            },
            "proposed_points": 0,
            "applied_points": 0,
            "proposed_action": "none",
            "decision_override": False,
            "reasons": [],
            "policy": {
                "max_corporate_hops": 3,
                "max_entities": 100,
                "graph_cap": MAX_GRAPH_POINTS,
                "related_action_threshold": 60,
                "minimum_strong_incidents": 2,
                "role_strength": ROLE_STRENGTH.copy(),
                "same_incident_counted_once": True,
                "own_entity_threshold": own_threshold,
                "own_window_hours": own_window_hours,
            },
        }
        if not self.enabled:
            return result
        paths, truncated = self.paths(document, at)
        result["relationships"]["related_entities"] = len(paths) - 1
        result["relationships"]["coverage"] = (
            "truncated" if truncated else ("registry_only" if self.registry else "unknown_without_registry")
        )
        points, counts, accounts, all_points = (
            defaultdict(int),
            defaultdict(int),
            defaultdict(set),
            defaultdict(int),
        )
        if not history_truncated:
            unique = {
                row.event_id: row
                for row in evidence
                if at - timedelta(hours=own_window_hours) < row.received_at <= at and row.increment > 0
            }
            for row in unique.values():
                # Inputs are independent, bounded own-account increments, never relationship assessments.
                if not 0 < row.increment <= 25:
                    raise ValueError("Own-evidence increments must be between 1 and 25")
                all_points[row.document] += row.increment
                if row.document not in paths:
                    continue
                if (
                    row.document != document
                    and row.document
                    not in self.paths(
                        document,
                        at,
                        occurred_at=row.received_at,
                    )[0]
                ):
                    continue
                points[row.document] += row.increment
                counts[row.document] += 1
                if row.account_identity is not None:
                    accounts[row.document].add(row.account_identity)
            if current_increment and current_event_id not in unique:
                if not 0 < current_increment <= 25:
                    raise ValueError("Current own increment must be between 1 and 25")
                points[document] += current_increment
                all_points[document] += current_increment
                counts[document] += 1
                if current_account_identity is not None:
                    accounts[document].add(current_account_identity)
            result["own_entity"].update(
                score=min(100, points[document]),
                risk_events=counts[document],
                accounts_with_evidence=len(accounts[document]),
                history_status="complete",
            )
        else:
            result["own_entity"]["history_status"] = "truncated"
        known_scores = (
            {}
            if history_truncated
            else {doc: min(100, all_points[doc]) for doc in self.documents(document, at, payments)}
        )
        result["financial_features"] = financial_features(
            document,
            at,
            payments,
            known_scores,
            truncated=payments_truncated,
        )
        relational = result["relationships"]
        # Keep max and top risks separate; clean entities cannot dilute strong evidence.
        # Heuristic corporate exposure is weaker than confirmed incident exposure.
        soft = sorted(
            ((min(100, value) * paths[doc][0], doc) for doc, value in points.items() if doc != document),
            reverse=True,
        )
        relational["max_related_untrust"] = round(soft[0][0], 2) if soft else 0
        relational["top_related_untrust"] = [round(score, 2) for score, _ in soft[:3]]
        incident_risks, strong_ids, own_ids = [], set(), set()
        own_severity = 0
        roots = {doc[:8] for _, doc in soft if len(doc) == 14}
        for incident in self.registry.incidents if self.registry else ():
            if not incident.available(at) or not any(doc in paths for doc in incident.documents):
                continue
            at_incident, incident_truncated = self.paths(document, at, occurred_at=incident.occurred_at)
            if truncated or incident_truncated:
                at_incident = {document: (1.0, ())}
            eligible = [doc for doc in incident.documents if doc in at_incident]
            if not eligible:
                continue
            best_document = max(eligible, key=lambda doc: at_incident[doc][0])
            weight, path = at_incident[best_document]
            severity = incident.severity * weight
            incident_risks.append(severity)
            if best_document == document:
                own_ids.add(incident.incident_id)
                own_severity = max(own_severity, incident.severity)
            if weight >= 0.75 and incident.severity >= 60:
                strong_ids.add(incident.incident_id)
            roots.update(doc[:8] for doc in eligible if len(doc) == 14 and doc != document)
            relational["evidence"].append(
                {
                    "incident_id": incident.incident_id,
                    "document": best_document,
                    "strength": weight,
                    "weighted_severity": severity,
                    "path": list(path),
                    "occurred_at": incident.occurred_at.isoformat(),
                    "reference": incident.reference,
                }
            )
        relational.update(
            confirmed_incidents=len(incident_risks),
            strong_confirmed_incidents=len(strong_ids),
            own_confirmed_incidents=len(own_ids),
            related_company_roots_with_evidence=len(roots),
        )
        strongest = max(incident_risks, default=0)
        corroboration = min(20, max(0, len(strong_ids) - 1) * 5) if strongest else 0
        relational["exposure_score"] = min(
            100,
            max(strongest + corroboration, relational["max_related_untrust"] * 0.5 if not truncated else 0),
        )
        exposure = relational["exposure_score"]
        result["proposed_points"] = min(MAX_GRAPH_POINTS, math.ceil(exposure * MAX_GRAPH_POINTS / 100))
        own_score = result["own_entity"]["score"]
        if own_score is not None and own_score >= own_threshold:
            result["reasons"].append("own_entity_untrust")
        if own_severity >= 60:
            result["reasons"].append("own_entity_confirmed_incident")
        if len(strong_ids) >= 2 and exposure >= 60:
            result["reasons"].append("verified_control_multiple_incidents")
        if result["reasons"]:
            result["proposed_action"] = "two_factor_required"
        return result


def combine_entity_risk(status, metadata, assessment):
    """Bound verified relationships to one factor; preserve independent evidence upstream."""
    original_status = status
    metadata = copy.deepcopy(metadata)
    assessment = copy.deepcopy(assessment)
    metadata["entity_risk"] = assessment
    if assessment["mode"] == "off":
        return status, metadata
    metadata["policy"]["entity_risk"] = {
        "mode": assessment["mode"],
        "registry_sha256": assessment["registry_sha256"],
        **assessment["policy"],
    }
    if assessment["mode"] != "contribute":
        return status, metadata
    metadata["policy"]["version"] += "+entity-risk-v1"
    before = metadata["risk_score"]
    proposed = assessment["proposed_points"]
    scoring = metadata["policy"]["scoring"]
    factor_weight = scoring["factor_weights"]["graph"]
    if proposed:
        match = RuleMatch(
            "verified_entity_relationship_exposure", assessment["relationships"]["exposure_score"], 0
        )
        rule = rule_evidence(match, "graph", proposed, factor_weight)
        metadata["triggered_rules"].append(rule)
        graph_rules = [r for r in metadata["triggered_rules"] if r["risk_factor"] == "graph"]
        factor = summarize_factor("graph", graph_rules, MAX_GRAPH_POINTS, factor_weight)
        factor["label"] = "Vínculos e evidências relacionais"
        metadata["risk_factors"] = [f for f in metadata["risk_factors"] if f["name"] != "graph"] + [factor]
        metadata["group_scores"]["graph"] = {k: factor[k] for k in ("raw_score", "score", "cap")}
        metadata["raw_score"] += proposed
        metadata["reasons"] = [r["code"] for r in metadata["triggered_rules"]]
        metadata.update(summarize_score(metadata["group_scores"], scoring))
    assessment["applied_points"] = metadata["risk_score"] - before
    proposed_status, source = score_decision(metadata, scoring)
    order = {"approved": 0, "two_factor_required": 1, "rejected": 2}
    if order[proposed_status] > order[status]:
        status, metadata["decision_source"] = proposed_status, source
    action_enabled = factor_weight > 0 or "own_entity_untrust" in assessment["reasons"]
    if status == "approved" and action_enabled and assessment["proposed_action"] == "two_factor_required":
        status, metadata["decision_source"] = "two_factor_required", "entity_risk"
    assessment["decision_override"] = status != original_status
    # Compare to the caller's decision without relaxing mandatory history controls.
    return status, metadata

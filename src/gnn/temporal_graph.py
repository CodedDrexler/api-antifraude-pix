"""V2 schema: typed directed relations, receipt-time evidence and temporal flow.

This schema is deliberately separate from the retired v1 model. Historical
non-rejected attempts are proxies, never proof of settlement or confirmed fraud.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from src.gnn.common import account_identity, money_feature, parse_date

FEATURE_VERSION = "pix-directed-temporal-v2"
RELATIONS = ("paid_to", "received_from", "uses_device", "used_by", "owns", "owned_by")
NODE_FEATURES = (
    "account",
    "holder",
    "device",
    "incoming_24h",
    "outgoing_24h",
    "incoming_holders",
    "outgoing_holders",
    "mean_incoming",
    "mean_outgoing",
    "account_age",
    "device_holders",
    "own_untrust",
    "own_risk_events",
    "incoming_1h",
    "outgoing_1h",
)
TRANSACTION_FEATURES = (
    "amount",
    "source_age",
    "destination_age",
    "payer_recent_attempts",
    "incoming_max_untrust",
    "outgoing_max_untrust",
    "incoming_suspect_fraction",
    "outgoing_suspect_fraction",
    "rapid_repass_pairs",
    "repass_fraction",
    "repasses_to_suspect_fraction",
    "device_holders",
)


@dataclass(frozen=True)
class GraphEvent:
    payload: dict
    received_at: datetime
    status: str
    own_increment: int = 0


@dataclass(frozen=True)
class TemporalGraph:
    x: np.ndarray
    edges: tuple[np.ndarray, ...]
    edge_weights: tuple[np.ndarray, ...]
    targets: np.ndarray
    transaction_features: np.ndarray
    history_count: int
    node_keys: tuple = ()


def build_temporal_graph(candidate, events, *, history_truncated=False, received_at=None, own_events=None):
    if history_truncated:
        raise ValueError("Incomplete history must not be scored as complete")
    at = parse_date(candidate["transaction_date"])
    # Offline callers simulate receipt at event time. Live callers supply the
    # server clock: a backdated Pix must not discard already received evidence.
    received_at = received_at or at
    unique = {}
    for event in events:
        row = event.payload
        event_at = parse_date(row["transaction_date"])
        if row["id"] == candidate["id"] or not at - timedelta(days=30) <= event_at <= at:
            continue
        if event.received_at > received_at:
            continue
        if type(event.own_increment) is not int or not 0 <= event.own_increment <= 25:
            raise ValueError("Only bounded independent own-account increments are accepted")
        if row["id"] in unique and unique[row["id"]] != event:
            raise ValueError("Conflicting historical event ID")
        unique[row["id"]] = event
    if len(unique) > 300:
        raise ValueError("History exceeds the experimental 300-event limit")
    history = sorted(
        unique.values(), key=lambda e: (parse_date(e.payload["transaction_date"]), e.payload["id"])
    )
    nodes, features, account_docs, account_nodes = {}, [], {}, {}
    incoming, outgoing, devices = {}, {}, {}
    links = [dict() for _ in RELATIONS]

    def node(key, kind):
        if key not in nodes:
            nodes[key] = len(nodes)
            values = np.zeros(len(NODE_FEATURES), dtype=np.float32)
            values[kind] = 1
            features.append(values)
        return nodes[key]

    def edge(relation, sender, receiver, weight=1.0):
        if sender != receiver:
            pair = (sender, receiver)
            links[relation][pair] = max(links[relation].get(pair, 0), weight)

    def account(value):
        key = account_identity(value)
        index = node(("account", *key), 0)
        doc = value["owner"]["document_number"]
        holder = node(("holder", doc), 1)
        edge(4, holder, index)
        edge(5, index, holder)
        age = max(0, (at - parse_date(value["opening_date"])).total_seconds() / 86400)
        features[index][9] = min(age / 30, 1)
        account_docs[index], account_nodes[key] = doc, index
        return index, holder

    source, holder = account(candidate["source_account"])
    destination, _ = account(candidate["destination_account"])
    device = node(("device", candidate["source"]["device_id"]), 2)
    # Candidate links are known now; candidate amount is never historical evidence.
    edge(0, source, destination)
    edge(1, destination, source)
    edge(2, source, device)
    edge(3, device, source)
    account_risk, holder_risk, account_counts, holder_counts = {}, {}, {}, {}
    payer_recent = 0
    for event in history:
        row = event.payload
        left, left_holder = account(row["source_account"])
        right, _ = account(row["destination_account"])
        elapsed = (at - parse_date(row["transaction_date"])).total_seconds()
        if account_docs[left] == account_docs[source] and elapsed <= 600:
            payer_recent += 1
        # A rejection can carry own evidence but must not create a money-flow edge.
        if event.status == "rejected":
            continue
        used_device = node(("device", row["source"]["device_id"]), 2)
        decay = 2 ** (-elapsed / (12 * 3600))
        edge(0, left, right, decay)
        edge(1, right, left, decay)
        edge(2, left, used_device, decay)
        edge(3, used_device, left, decay)
        if elapsed < 86400 and event.received_at > received_at - timedelta(hours=24):
            devices.setdefault(used_device, set()).add(account_docs[left])
            if left != right:
                outgoing.setdefault(left, []).append(event)
                incoming.setdefault(right, []).append(event)

    # Live own-account evidence is queried separately by receipt time. Its
    # existence must not depend on the caller's event clock or neighborhood cut.
    own = {}
    for event in history if own_events is None else own_events:
        if event.payload["id"] == candidate["id"]:
            continue
        if not received_at - timedelta(hours=24) < event.received_at <= received_at:
            continue
        if type(event.own_increment) is not int or not 0 <= event.own_increment <= 25:
            raise ValueError("Only bounded independent own-account increments are accepted")
        event_id = event.payload["id"]
        if event_id in own and own[event_id] != event:
            raise ValueError("Conflicting own-evidence event ID")
        own[event_id] = event
    if own_events is not None and len(own) > 300:
        raise ValueError("Own-evidence history exceeds the live 300-event limit")
    for event in own.values():
        if not event.own_increment:
            continue
        left, left_holder = account(event.payload["source_account"])
        account_risk[left] = account_risk.get(left, 0) + event.own_increment
        holder_risk[left_holder] = holder_risk.get(left_holder, 0) + event.own_increment
        account_counts[left] = account_counts.get(left, 0) + 1
        holder_counts[left_holder] = holder_counts.get(left_holder, 0) + 1

    for index, events_in in incoming.items():
        features[index][3] = min(len(events_in) / 20, 1)
        features[index][5] = min(
            len({e.payload["source_account"]["owner"]["document_number"] for e in events_in}) / 20, 1
        )
        features[index][7] = money_feature(sum(e.payload["amount"] for e in events_in) / len(events_in))
        features[index][13] = min(
            sum((at - parse_date(e.payload["transaction_date"])).total_seconds() <= 3600 for e in events_in)
            / 10,
            1,
        )
    for index, events_out in outgoing.items():
        features[index][4] = min(len(events_out) / 20, 1)
        features[index][6] = min(
            len({e.payload["destination_account"]["owner"]["document_number"] for e in events_out}) / 20, 1
        )
        features[index][8] = money_feature(sum(e.payload["amount"] for e in events_out) / len(events_out))
        features[index][14] = min(
            sum((at - parse_date(e.payload["transaction_date"])).total_seconds() <= 3600 for e in events_out)
            / 10,
            1,
        )
    for index, owners in devices.items():
        features[index][10] = min(len(owners) / 10, 1)
    for risks, counts in ((account_risk, account_counts), (holder_risk, holder_counts)):
        for index, points in risks.items():
            features[index][11] = min(points, 100) / 100
            features[index][12] = min(counts[index] / 4, 1)

    def contacts(events_in, direction):
        docs = {e.payload[direction + "_account"]["owner"]["document_number"] for e in events_in}
        scores = [min(holder_risk.get(nodes[("holder", doc)], 0), 100) / 100 for doc in docs]
        return max(scores, default=0), sum(s >= 0.4 for s in scores) / max(len(scores), 1)

    incoming_rows, outgoing_rows = incoming.get(source, []), outgoing.get(source, [])
    in_max, in_fraction = contacts(incoming_rows, "source")
    out_max, out_fraction = contacts(outgoing_rows, "destination")
    available, repasses, risky_repasses = [], 0, 0
    for event in sorted(
        incoming_rows + outgoing_rows,
        key=lambda e: (parse_date(e.payload["transaction_date"]), e.payload["id"]),
    ):
        row = event.payload
        if account_identity(row["destination_account"]) == account_identity(candidate["source_account"]):
            available.append(event)
            continue
        matches = [
            e
            for e in available
            if 0
            < (
                parse_date(row["transaction_date"]) - parse_date(e.payload["transaction_date"])
            ).total_seconds()
            <= 1800
            and 4 * e.payload["amount"] <= 5 * row["amount"]
            and 4 * row["amount"] <= 5 * e.payload["amount"]
            and e.payload["source_account"]["owner"]["document_number"]
            != row["destination_account"]["owner"]["document_number"]
        ]
        if matches:
            available.remove(max(matches, key=lambda e: parse_date(e.payload["transaction_date"])))
            repasses += 1
            target_holder = nodes[("holder", row["destination_account"]["owner"]["document_number"])]
            risky_repasses += holder_risk.get(target_holder, 0) >= 40
    transaction_features = np.array(
        [
            money_feature(candidate["amount"]),
            features[source][9],
            features[destination][9],
            min(payer_recent / 10, 1),
            in_max,
            out_max,
            in_fraction,
            out_fraction,
            min(repasses / 4, 1),
            repasses / max(len(incoming_rows), 1),
            risky_repasses / max(repasses, 1),
            min(len(devices.get(device, set()) | {account_docs[source]}) / 10, 1),
        ],
        dtype=np.float32,
    )
    return TemporalGraph(
        np.array(features, dtype=np.float32),
        tuple(np.array(sorted(items), dtype=np.int64).reshape(-1, 2).T for items in links),
        tuple(np.array([items[pair] for pair in sorted(items)], dtype=np.float32) for items in links),
        np.array([source, destination, device, holder]),
        transaction_features,
        sum(event.status != "rejected" for event in history),
        tuple(nodes),
    )


def relation_mean(x, edges, weights):
    result = np.zeros_like(x)
    counts = np.zeros((len(x), 1), dtype=np.float32)
    if edges.shape[1]:
        np.add.at(result, edges[1], x[edges[0]] * weights[:, None])
        np.add.at(counts, edges[1], 1)
    return result / np.maximum(counts, 1)

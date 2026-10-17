"""Point-in-time graph features shared by training and online inference."""

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

FEATURE_VERSION = "pix-graph-v1"
NODE_FEATURES = 10
TRANSACTION_FEATURES = 4


def account_identity(account):
    return (
        account.get("participant") or "",
        account["branch"],
        account["account_number"],
        account["owner"]["document_number"],
    )


def parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def money_feature(value):
    return min(math.log1p(max(value, 0)) / 16, 1.5)


@dataclass
class Graph:
    x: np.ndarray
    edges: np.ndarray
    targets: np.ndarray
    transaction_features: np.ndarray
    history_count: int


def build_graph(candidate: dict, history: list[dict]) -> Graph:
    at = parse_date(candidate["transaction_date"])
    # Exclude retries and future events even when the caller supplied unsorted data.
    unique = {
        record["id"]: record
        for record in history
        if record["id"] != candidate["id"] and parse_date(record["transaction_date"]) <= at
    }
    history = sorted(unique.values(), key=lambda row: (row["transaction_date"], row["id"]))
    nodes = {}
    kinds, incoming, outgoing, in_amount, out_amount, neighbors, users, ages = ([] for _ in range(8))
    edges = set()

    def node(key, kind, age=0):
        if key not in nodes:
            nodes[key] = len(nodes)
            kinds.append(kind)
            incoming.append(0)
            outgoing.append(0)
            in_amount.append(0)
            out_amount.append(0)
            neighbors.append(set())
            users.append(set())
            ages.append(age)
        return nodes[key]

    def account(account):
        age = max(0, (at - parse_date(account["opening_date"])).total_seconds() / 86400)
        return node(("account", *account_identity(account)), "account", age)

    def connect(left, right):
        if left != right:
            edges.add((left, right))
            edges.add((right, left))

    source = account(candidate["source_account"])
    destination = account(candidate["destination_account"])
    device = node(("device", candidate["source"]["device_id"]), "device")
    recent = 0
    for row in history:
        sender, receiver = account(row["source_account"]), account(row["destination_account"])
        used_device = node(("device", row["source"]["device_id"]), "device")
        connect(sender, receiver)
        connect(sender, used_device)
        outgoing[sender] += 1
        incoming[receiver] += 1
        out_amount[sender] += row["amount"]
        in_amount[receiver] += row["amount"]
        neighbors[sender].add(receiver)
        neighbors[receiver].add(sender)
        users[used_device].add(sender)
        if (
            row["source_account"]["owner"]["document_number"]
            == candidate["source_account"]["owner"]["document_number"]
        ):
            if (at - parse_date(row["transaction_date"])).total_seconds() <= 600:
                recent += 1
    # Candidate relations are known at request time; its amount never enters historical counts.
    connect(source, destination)
    connect(source, device)
    x = np.array(
        [
            [
                float(kind == "account"),
                float(kind == "device"),
                min(incoming[i] / 20, 1),
                min(outgoing[i] / 20, 1),
                min(len(neighbors[i]) / 20, 1),
                min(len(users[i]) / 10, 1),
                money_feature(in_amount[i] / max(incoming[i], 1)),
                money_feature(out_amount[i] / max(outgoing[i], 1)),
                min(ages[i] / 30, 1),
                min((incoming[i] + outgoing[i]) / 30, 1),
            ]
            for i, kind in enumerate(kinds)
        ],
        dtype=np.float32,
    )
    edge_array = np.array(sorted(edges), dtype=np.int64).T if edges else np.zeros((2, 0), dtype=np.int64)
    transaction_features = np.array(
        [
            money_feature(candidate["amount"]),
            min(ages[source] / 30, 1),
            min(ages[destination] / 30, 1),
            min(recent / 10, 1),
        ],
        dtype=np.float32,
    )
    return Graph(x, edge_array, np.array([source, destination, device]), transaction_features, len(history))


def neighbor_mean(x, edges):
    result = np.zeros_like(x)
    counts = np.zeros((len(x), 1), dtype=np.float32)
    if edges.shape[1]:
        np.add.at(result, edges[1], x[edges[0]])
        np.add.at(counts, edges[1], 1)
    return result / np.maximum(counts, 1)

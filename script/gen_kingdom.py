"""
Generate kingdom/data/kingdom_data.json ("数学王国地图") from a mathlib4
`lake exe graph` import_graph.dot export.

This is a sibling pipeline to gen_graph.py, not a replacement: it shares the
same upstream `import_graph.dot`, but produces a completely independent
JSON artifact (schema documented in kingdom/schema.md). Rendering is
intentionally out of scope here -- see kingdom/schema.md for the contract.

Usage (run with cwd = repo root, same convention as gen_graph.py):
    python script/gen_kingdom.py
"""
import os
import re
import sys
import math
import json
import hashlib
import datetime
import networkx as nx
import numpy as np
import yaml

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
mathlib_src_path = os.path.abspath(os.path.join(REPO_ROOT, '..', 'mathlib4'))
graph_path = os.path.join(mathlib_src_path, 'import_graph.dot')
toolchain_path = os.path.join(mathlib_src_path, 'lean-toolchain')
regions_config_path = os.path.join(REPO_ROOT, 'kingdom', 'regions.yaml')
overrides_config_path = os.path.join(REPO_ROOT, 'kingdom', 'tier_overrides.yaml')
output_path = os.path.join(REPO_ROOT, 'kingdom', 'data', 'kingdom_data.json')

FRONTIER_REGION = {
    'id': 'frontier', 'name': '未知边境', 'color': '#202020',
    'is_summit_layer': False, 'is_meta': False, 'tier_count': 3,
    'namespace_prefixes': [],
}
SKY_BASE_TIER = 100  # any summit-layer macro_tier is offset above this
LOCAL_SPREAD_FACTOR = 2.6  # per-region footprint radius = this * sqrt(node_count)
MOUNTAIN_MARGIN = 10.0  # minimum gap kept between any two mountains' footprints
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))


# ---------------------------------------------------------------------------
# 1. Parse import_graph.dot
#    (handles both "a" -> "b"; edges and the newer "x" [shape=ellipse];
#    isolated-node declaration lines that the current importGraph exporter
#    emits for sink nodes with no outgoing edges.)
# ---------------------------------------------------------------------------
edge_re = re.compile(r'^"(.+)" -> "(.+)";?$')
node_re = re.compile(r'^"(.+)" \[shape=ellipse\];?$')

G = nx.DiGraph()
with open(graph_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        m = edge_re.match(line)
        if m:
            G.add_edge(m.group(1), m.group(2))
            continue
        m = node_re.match(line)
        if m:
            G.add_node(m.group(1))

if 'Mathlib' in G:
    G.remove_node('Mathlib')

print(f'# of nodes: {G.number_of_nodes()}')
print(f'# of edges: {G.number_of_edges()}')

# NOTE on edge direction: a dot edge "u" -> "v" means v imports u, i.e.
# v depends on u (u is upstream/foundational, v is downstream/built-on-top).
# This is the same convention gen_graph.py relies on (nx.ancestors(node) is
# used there as "the set of things node depends on").


# ---------------------------------------------------------------------------
# 2. Load region config + tier overrides
# ---------------------------------------------------------------------------
with open(regions_config_path, 'r', encoding='utf-8') as f:
    regions_cfg = yaml.safe_load(f)['regions']
for r in regions_cfg:
    r.setdefault('is_meta', False)

with open(overrides_config_path, 'r', encoding='utf-8') as f:
    tier_overrides = yaml.safe_load(f).get('overrides') or {}


def assign_region(node):
    for r in regions_cfg:
        for prefix in r['namespace_prefixes']:
            if node.startswith(f'Mathlib.{prefix}.'):
                return r['id']
    return FRONTIER_REGION['id']


region_by_id = {r['id']: r for r in regions_cfg}
region_by_id[FRONTIER_REGION['id']] = FRONTIER_REGION

node_region = {n: assign_region(n) for n in G.nodes}

nodes_by_region = {}
for n, rid in node_region.items():
    nodes_by_region.setdefault(rid, []).append(n)


# ---------------------------------------------------------------------------
# 3. Global reverse-PageRank (reused both as node "size" and as one of the
#    two macro_tier heuristic signals -- same computation gen_graph.py
#    already relies on for node radius).
# ---------------------------------------------------------------------------
page_rank = nx.pagerank(G.reverse())
pr_max, pr_min = max(page_rank.values()), min(page_rank.values())


def stable_hash01(name):
    """Deterministic hash -> [0, 1), stable across processes/platforms
    (unlike builtin hash(), which is salted per-process)."""
    h = hashlib.md5(name.encode('utf-8')).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def cluster_key(node, depth=3):
    parts = node.split('.')
    return '.'.join(parts[:min(len(parts), depth)])


# ---------------------------------------------------------------------------
# 4. Per-region computation: micro_elevation (local dependency depth) and
#    the macro_tier heuristic (unification breadth + reverse-pagerank).
# ---------------------------------------------------------------------------
node_data = {}  # id -> dict of computed fields (filled in below)
region_footprint_radius = {}  # rid -> exact bounding radius of its node spread

for rid, members in nodes_by_region.items():
    region = region_by_id[rid]
    sub = G.subgraph(members)
    topo = list(nx.topological_sort(sub))

    # --- micro_elevation: longest path depth from region-local roots ---
    depth = {}
    for n in topo:
        preds = list(sub.predecessors(n))
        depth[n] = 0 if not preds else 1 + max(depth[p] for p in preds)
    max_depth = max(depth.values()) if depth else 0
    micro_elevation = {n: (depth[n] / max_depth if max_depth > 0 else 0.0) for n in members}

    # --- unification breadth: distinct sub-theory clusters among a node's
    #     descendants, computed bottom-up in reverse topological order so
    #     each node's cluster-set is a single union of its direct
    #     successors' already-computed sets (O(V+E), no repeated traversal)
    desc_clusters = {}
    for n in reversed(topo):
        s = set()
        for succ in sub.successors(n):
            s.add(cluster_key(succ))
            s |= desc_clusters[succ]
        desc_clusters[n] = s
    unification_breadth = {n: len(desc_clusters[n]) for n in members}

    # --- combine + normalize within region, then quantile-bin into tiers ---
    ub_vals = np.array([unification_breadth[n] for n in members], dtype=float)
    pr_vals = np.array([(page_rank[n] - pr_min) / (pr_max - pr_min) if pr_max > pr_min else 0.0
                         for n in members], dtype=float)
    ub_norm = (ub_vals - ub_vals.min()) / (ub_vals.max() - ub_vals.min()) if ub_vals.max() > ub_vals.min() else ub_vals * 0
    score = 0.5 * ub_norm + 0.5 * pr_vals

    tier_count = region['tier_count']
    boundaries = np.unique(np.percentile(score, np.linspace(0, 100, tier_count + 1)))
    if len(boundaries) < 2:
        tiers = np.zeros(len(score), dtype=int)
    else:
        tiers = np.clip(np.digitize(score, boundaries[1:-1], right=True), 0, len(boundaries) - 2)

    # --- local planar spread: a bounded polar disc (radius = normalized
    #     micro_elevation, angle = a stable hash) so every region's
    #     footprint has an exact, predictable radius -- this is what makes
    #     guaranteed non-overlapping mountain placement possible below.
    #     Scaling by sqrt(region size) keeps node density comparable
    #     across differently-sized mountains. ---
    footprint_radius = LOCAL_SPREAD_FACTOR * max(1.0, len(members) ** 0.5)
    region_footprint_radius[rid] = footprint_radius

    for i, n in enumerate(members):
        angle = stable_hash01(n) * 2 * math.pi
        local_r = micro_elevation[n] * footprint_radius
        node_data[n] = {
            'region_id': rid,
            'micro_elevation': micro_elevation[n],
            'macro_tier_score': float(score[i]),
            'macro_tier_heuristic': int(tiers[i]),
            'local_depth': depth[n],
            'local_x': local_r * math.cos(angle),
            'local_z': local_r * math.sin(angle),
        }

# apply summit-layer tier offset
for rid, members in nodes_by_region.items():
    if region_by_id[rid]['is_summit_layer']:
        for n in members:
            node_data[n]['macro_tier_heuristic'] += SKY_BASE_TIER

# apply manual overrides
for n, override_tier in tier_overrides.items():
    if n in node_data:
        node_data[n]['macro_tier_override'] = int(override_tier)
    else:
        print(f'WARNING: tier_overrides.yaml references unknown node {n!r}, ignoring')
for n in node_data:
    node_data[n].setdefault('macro_tier_override', None)
    node_data[n]['macro_tier'] = (
        node_data[n]['macro_tier_override']
        if node_data[n]['macro_tier_override'] is not None
        else node_data[n]['macro_tier_heuristic']
    )


# ---------------------------------------------------------------------------
# 5. Region map layout: place every ground mountain with a guaranteed
#    non-overlapping golden-angle spiral packing (each region's footprint
#    is an exact circle of radius region_footprint_radius[rid], so two
#    regions overlap iff the distance between their centers is less than
#    the sum of their radii + margin -- this is checked explicitly below,
#    not left to a force-directed layout that ignores footprint size).
#    Regions are placed largest-first so the biggest mountain anchors the
#    center of the map and smaller ones spiral out around it.
# ---------------------------------------------------------------------------
ground_region_ids = [rid for rid, r in region_by_id.items() if not r['is_summit_layer']]
ground_region_ids.sort(key=lambda rid: -len(nodes_by_region.get(rid, [])))

placed_circles = []  # list of (x, z, radius)
map_center = {}
for rid in ground_region_ids:
    r = region_footprint_radius.get(rid, LOCAL_SPREAD_FACTOR)
    if not placed_circles:
        map_center[rid] = (0.0, 0.0)
        placed_circles.append((0.0, 0.0, r))
        continue
    t = 0
    while True:
        t += 1
        angle = t * GOLDEN_ANGLE
        dist = 3.0 * math.sqrt(t)
        x, z = dist * math.cos(angle), dist * math.sin(angle)
        if all(math.hypot(x - px, z - pz) >= (pr + r + MOUNTAIN_MARGIN) for px, pz, pr in placed_circles):
            map_center[rid] = (x, z)
            placed_circles.append((x, z, r))
            break

# cross-region edge counts are no longer used to drive placement (guaranteed
# separation now takes priority over connectivity-based proximity), but are
# still reported in bridge_summary further down from the raw edge list.


# ---------------------------------------------------------------------------
# 6. Summit-layer node placement: weighted centroid of the map_centers of
#    the (non-summit) regions that depend on each summit node, computed in
#    a single pass over all edges (rather than per-node successor scans).
# ---------------------------------------------------------------------------
summit_region_ids = {rid for rid in nodes_by_region if region_by_id[rid]['is_summit_layer']}
summit_dependent_weight = {}  # node -> {region_id: count}
for u, v in G.edges():
    # v depends on u; if u is a summit node and v's region differs, v's region "uses" u
    if node_region.get(u) in summit_region_ids and node_region[v] not in summit_region_ids:
        summit_dependent_weight.setdefault(u, {})
        summit_dependent_weight[u][node_region[v]] = summit_dependent_weight[u].get(node_region[v], 0) + 1

fallback_center = (
    float(np.mean([c[0] for c in map_center.values()])) if map_center else 0.0,
    float(np.mean([c[1] for c in map_center.values()])) if map_center else 0.0,
)

for n in node_data:
    if node_data[n]['region_id'] in summit_region_ids:
        weights = summit_dependent_weight.get(n)
        if weights:
            total = sum(weights.values())
            cx = sum(map_center[r][0] * w for r, w in weights.items()) / total
            cz = sum(map_center[r][1] * w for r, w in weights.items()) / total
            node_data[n]['x'] = cx + node_data[n]['local_z']
            node_data[n]['z'] = cz + node_data[n]['local_depth']
        else:
            node_data[n]['x'] = fallback_center[0] + node_data[n]['local_z']
            node_data[n]['z'] = fallback_center[1] + node_data[n]['local_depth']
    else:
        cx, cz = map_center[node_data[n]['region_id']]
        node_data[n]['x'] = cx + node_data[n]['local_x']
        node_data[n]['z'] = cz + node_data[n]['local_z']


# ---------------------------------------------------------------------------
# 7. Assemble output
# ---------------------------------------------------------------------------
toolchain = ''
if os.path.exists(toolchain_path):
    with open(toolchain_path, 'r', encoding='utf-8') as f:
        toolchain = f.read().strip()

regions_out = []
for rid, r in region_by_id.items():
    regions_out.append({
        'id': rid,
        'name': r['name'],
        'color': r['color'],
        'is_summit_layer': r['is_summit_layer'],
        'is_meta': r['is_meta'],
        'map_center': None if r['is_summit_layer'] else {
            'x': map_center[rid][0], 'z': map_center[rid][1],
        },
        'footprint_radius': region_footprint_radius.get(rid),
        'tier_count': r['tier_count'],
        'node_count': len(nodes_by_region.get(rid, [])),
    })

nodes_out = []
for n, d in node_data.items():
    rank = page_rank[n]
    size = 0.2 + 3 * ((rank - pr_min) / (pr_max - pr_min)) ** 0.5 if pr_max > pr_min else 0.2
    nodes_out.append({
        'id': n,
        'region_id': d['region_id'],
        'micro_elevation': round(d['micro_elevation'], 4),
        'macro_tier': d['macro_tier'],
        'macro_tier_score': round(d['macro_tier_score'], 4),
        'macro_tier_override': d['macro_tier_override'],
        'x': round(d['x'], 3),
        'z': round(d['z'], 3),
        'size': round(size, 4),
    })

edges_out = []
bridge_summary_counter = {}
for u, v in G.edges():
    from_n, to_n = v, u  # v depends on u
    from_region, to_region = node_region[v], node_region[u]
    is_bridge = from_region != to_region
    edges_out.append({'from': from_n, 'to': to_n, 'is_bridge': is_bridge})
    if is_bridge:
        key = (from_region, to_region)
        bridge_summary_counter[key] = bridge_summary_counter.get(key, 0) + 1

bridge_summary_out = [
    {'from_region': ra, 'to_region': rb, 'edge_count': cnt}
    for (ra, rb), cnt in sorted(bridge_summary_counter.items(), key=lambda kv: -kv[1])
]

output = {
    'meta': {
        'source': 'mathlib4',
        'toolchain': toolchain,
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'node_count': len(nodes_out),
        'edge_count': len(edges_out),
    },
    'regions': regions_out,
    'nodes': nodes_out,
    'edges': edges_out,
    'bridge_summary': bridge_summary_out,
}

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=None)

print(f'wrote {output_path}')


# ---------------------------------------------------------------------------
# 8. Sanity report
# ---------------------------------------------------------------------------
print('\n--- per-region tier histogram ---')
for r in regions_out:
    rid = r['id']
    tiers = [n['macro_tier'] for n in nodes_out if n['region_id'] == rid]
    if not tiers:
        continue
    hist = {}
    for t in tiers:
        hist[t] = hist.get(t, 0) + 1
    print(f"{r['name']:12s} ({rid:20s}) n={len(tiers):5d} tiers={dict(sorted(hist.items()))}")

print('\n--- top bridge_summary pairs ---')
for b in bridge_summary_out[:10]:
    print(f"  {b['from_region']:20s} -> {b['to_region']:20s}: {b['edge_count']}")

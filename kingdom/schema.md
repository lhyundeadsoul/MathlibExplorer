# 数学王国地图 —— 数据格式(`kingdom_data.json`)

这份文档是**数据生成模块**(`script/gen_kingdom.py`)和**渲染模块**(目前尚未实现,未来可以是任何语言/引擎)之间唯一的契约。渲染器只需要读这份 JSON,完全不需要知道 mathlib、Lean、networkx 的存在。

数据由 `script/gen_kingdom.py` 从 mathlib4 的 `lake exe graph` 产出的 `import_graph.dot` 生成,山脉(区域)划分规则在 `kingdom/regions.yaml`,人工层级覆盖在 `kingdom/tier_overrides.yaml`。

## 顶层结构

```json
{
  "meta": { ... },
  "regions": [ ... ],
  "nodes": [ ... ],
  "edges": [ ... ],
  "bridge_summary": [ ... ]
}
```

### `meta`

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | string | 固定为 `"mathlib4"` |
| `toolchain` | string | 生成数据时 mathlib4 的 `lean-toolchain` 版本,如 `"leanprover/lean4:v4.32.0-rc1"` |
| `generated_at` | string (ISO 8601) | 生成时间戳 |
| `node_count` / `edge_count` | int | 冗余字段,方便渲染器/校验脚本快速核对而不用数组长度 |

### `regions[]` —— 山脉

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 唯一标识,对应 `kingdom/regions.yaml` 里的 `id`,或 fallback 区域 `"frontier"` |
| `name` | string | 显示名称,如 "代数山" |
| `color` | string (hex) | 建议配色 |
| `is_summit_layer` | bool | true = 悬浮在其他山脉之上的"天空层"(目前只有 `category_theory`) |
| `is_meta` | bool | true = 非数学内容,元编程/证明工具箱(目前只有 `tactic`) |
| `map_center` | `{x, z}` \| `null` | 这座山在地图平面上的中心坐标。**天空层区域此字段为 `null`**——它没有自己的地面位置,坐标要看它下面挂的节点各自的 `x, z`(见下) |
| `footprint_radius` | float \| `null` | 这座山脉节点分布的精确边界半径(`= LOCAL_SPREAD_FACTOR * sqrt(node_count)`,天空层为 `null`)。**山脉之间保证 `distance(centerA, centerB) >= footprint_radiusA + footprint_radiusB + margin`**,渲染器画"领地范围"时应该用这个精确值,而不是自己估算,否则可能画得比实际节点分布小,让节点看起来"溢出" |
| `tier_count` | int | 这座山脉大海拔的层数 |
| `node_count` | int | 落在这个区域里的节点数(冗余,便于校验) |

### `nodes[]` —— mathlib 模块 = 地图上的一个点

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 完整 mathlib 模块名,如 `"Mathlib.Algebra.Group.Defs"` |
| `region_id` | string | 所属山脉,对应 `regions[].id` |
| `micro_elevation` | float, 0.0–1.0 | **小海拔**:区域内最长依赖路径深度,归一化到 0~1。若 a 依赖 b,则 `micro_elevation(b) < micro_elevation(a)`(在同一区域内严格保证;跨区域依赖不参与这个排序,由 `is_bridge` 边表达) |
| `macro_tier` | int | **大海拔**:离散层级,范围 `[0, tier_count)`;天空层节点固定为 `SKY_BASE_TIER + 区域内局部 tier`(`SKY_BASE_TIER = 100`,保证任何天空层节点的 `macro_tier` 都高于任何地面山脉),用来保证"范畴论永远悬浮在所有地面山脉之上" |
| `macro_tier_score` | float | 分箱之前的连续启发式分数(见下方"大海拔启发式"),保留下来是为了以后调整分箱边界或做手工校准时可以复查 |
| `macro_tier_override` | int \| `null` | 非 `null` 时表示这个层级来自 `kingdom/tier_overrides.yaml` 的人工指定,而不是启发式计算 |
| `x`, `z` | float | 节点在地图平面上的坐标。地面山脉节点:`map_center` + 一个半径不超过 `footprint_radius` 的局部极坐标偏移(半径 = 归一化的 `micro_elevation`,角度 = 节点名的稳定哈希),保证同一座山的所有节点都落在它自己的 `footprint_radius` 圆内,不会侵入相邻山脉。天空层节点:其**依赖方各区域 `map_center` 按引用次数加权的质心**——被代数大量引用的范畴论节点,坐标会漂移到代数山上空 |
| `size` | float | 节点大小,直接复用 `gen_graph.py` 里已经在算的全局反向 PageRank 半径公式 |
| `title` | string \| `null` | 从 mathlib4 源码里对应 `.lean` 文件的模块级 `/-! ... -/` 文档注释中提取的标题(真实内容,不是生成的)。文件不存在或没有模块文档时为 `null` |
| `summary` | string \| `null` | 同一个文档注释里标题之后的正文,截到下一个 `##` 子标题之前,并裁剪到 `SUMMARY_MAX_LEN`(420 字符)。同样是真实的 mathlib 源码内容 |
| `doc_url` | string | 对应的 [mathlib4_docs](https://leanprover-community.github.io/mathlib4_docs/) 页面链接,按 `id` 里的点号转斜杠拼出来,不依赖 `title`/`summary` 是否提取成功,总是有值 |

### `edges[]` —— import 依赖

| 字段 | 类型 | 说明 |
|---|---|---|
| `from`, `to` | string | 模块名,`from` 依赖 `to`(`from` 的 `micro_elevation`/`macro_tier` 应该 ≥ `to`,同区域内严格保证) |
| `is_bridge` | bool | `region_id(from) != region_id(to)` 时为 true,即跨山脉的边——地图上画成连接两座山峰的桥梁 |

### `bridge_summary[]` —— 粗粒度桥梁汇总

```json
{"from_region": "category_theory", "to_region": "algebra", "edge_count": 143}
```

按 `(from_region, to_region)` 聚合的跨区边数量,渲染器可以只画这张汇总表里排名靠前的"主桥",而不必渲染全部两万条边里的每一条跨区边。

## 山脉布局算法 —— 保证互不重叠

每座地面山脉的节点分布被约束在一个半径精确等于 `footprint_radius` 的圆盘内(节点局部坐标用极坐标生成:半径 = 归一化 `micro_elevation` × `footprint_radius`,角度 = 节点名的稳定哈希)。有了这个精确边界,山脉中心 `map_center` 就可以用一个简单的黄金角螺旋摆放算法逐个放置:按节点数从大到小排序,依次沿螺旋线寻找第一个满足 `distance(新山, 已放置的每一座山) >= 两者 footprint_radius 之和 + 10` 的位置。这保证了**任意两座地面山脉的节点分布圆盘一定不重叠**,代价是不再像早期版本那样用"跨区边数量"驱动布局去让联系紧密的山脉互相靠近——保证不重叠现在优先于这一点。跨区边的强弱关系仍然完整保留在 `bridge_summary` 里,只是不再影响山脉摆放位置。

## 大海拔(`macro_tier`)启发式 —— 已知局限性,请务必阅读

大海拔本应表达"这一层比上一层在做**推广(Generalization)/统一(Unification)/遗忘(Abstraction)**"当中至少两条,这是一个数学教学法/编辑判断,**不是能从 import 依赖图直接算出来的东西**。当前实现用两个图论信号近似:

1. **统一广度**(近似 Unification):把区域内节点按第三级命名空间分成若干"子理论簇"(比如代数山里 `Group`/`Ring`/`Field`/`NumberTheory` 各是一簇),统计有多少个不同的子理论簇最终依赖于某节点。依赖它的子簇越多,越像是在"缝合"多条原本独立的理论。
2. **奠基广度**(近似 Generalization/Abstraction):直接复用 `gen_graph.py` 里已经在算的反向 PageRank——有多少东西直接或间接建立在它之上。

`macro_tier_score = normalize(统一广度) + normalize(奠基广度)`,再用分位数分箱(`numpy.percentile`,箱数取 `regions.yaml` 里的 `tier_count`)映射成整数 `macro_tier`。

**这套启发式大概率不会精确复现"数 → 同余 → 群 → 环 → 域 → Galois"这种叙事**。典型的失配例子:mathlib 里 `Nat`/`Int` 这类具体数系的反向 PageRank 几乎是全库最高(几乎所有东西都直接或间接用到自然数),启发式会把它们排得比 `Group.Defs` 更"奠基",但这不代表 `Nat` 在数学抽象阶梯上应该排在 `Group` 之上——恰恰相反,用户设想的阶梯里 `Nat` 应该在最底层。

因此:

- `macro_tier_score` 字段被完整保留在输出里,方便以后复查/重新分箱。
- 任何时候想手工纠正,不需要改数据格式或重写生成逻辑——直接在 `kingdom/tier_overrides.yaml` 里给该模块指定一个层级,重新跑一次 `gen_kingdom.py` 即可,该节点的 `macro_tier` 会直接取覆盖值,`macro_tier_override` 字段也会同步记录这一点。
- 目前 `tier_overrides.yaml` 是空的,这是本阶段有意为之的产物——数据管线已经打好地基,数学内容的人工校准是下一阶段的工作。

## 与现有 2D 数据管线的关系

`kingdom_data.json` 是一条完全独立的数据管线,和现有的 `script/gen_graph.py` / `release/data/import_graph.txt` / bgfx 渲染器**互不影响、互不依赖**。两者共享同一份上游数据来源(`lake exe graph` 生成的 `import_graph.dot`),但下游各自处理,互相之间没有代码或数据格式上的耦合。

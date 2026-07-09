# MathlibExplorer

Mathlib explorer is an interactive visualization tool designed for [Lean's mathlib library](https://github.com/leanprover-community/mathlib4). It visualizes the import relations within mathlib, with carefully thought-out layout and interactions. It is a great visual representation of how math concepts are connected to each other, which can be informative even if you cannot read Lean code.

Related video series (in Chinese):

欢迎关注相关视频系列：《重构数学》on [bilibili](https://space.bilibili.com/613069855) and [YouTube](https://www.youtube.com/@yugu233/videos).

Screenshots:
![Mathlib Explorer](./screenshots/default_view.png)

Zoom in view:
![Zoom in view](./screenshots/zoom_in_view.png)

## Features

The import graph is mapped onto the plane, s.t. if B imports A, B will always be on the right of A. This makes it easy to see how modern math theories are constructed from axioms and definitions.

Supported interactions:

- Scroll to zoom in/out
- Drag to move
- Click on a node to highlight
  - its direct neighbors
  - its transitive dependents
  - its transitive dependencies
- Click on a topic label to highlight
  - all nodes in the same topic
  - references to the topic
  - direct dependencies of the topic

## Usage

Clone this repo:

```
git clone https://github.com/Crispher/MathlibExplorer
```

Run it with one command from the repo root, picking `2d` for the original bgfx import-graph explorer or `3d` for the experimental [3D "mathematical kingdom" map](./kingdom/):

```
cd MathlibExplorer

# macOS / Linux
./run.sh 2d
./run.sh 3d

# Windows
run.bat 2d
run.bat 3d
```

(There is currently no prebuilt Linux binary for the 2D explorer, only macOS and Windows; `run.sh 2d` will tell you so instead of failing silently. The 3D map only needs a browser and works everywhere.)

Or run the 2D explorer's executable directly:

```
cd MathlibExplorer/release/bin_{YOUR_PLATFORM}
./MathlibExplorer
```

## Other Notes

Limited testing has been done so far, which is mainly on MacOS (M1).

The underlying mathlib data is a bit outdated. I might update it or publish the scripts to generate the data in the future.

Cross-platform graphics is powered by [bgfx](https://github.com/bkaradzic/bgfx).

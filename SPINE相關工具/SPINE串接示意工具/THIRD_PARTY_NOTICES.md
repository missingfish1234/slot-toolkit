# Offline dependencies

Files in vendor are redistributed without source edits; copyright/license headers in the files are retained.

- PixiJS 7.3.2 — MIT — https://github.com/pixijs/pixijs
- @pixi-spine/all-3.8, all-4.0, all-4.1 version 4.0.6 — https://github.com/pixijs-userland/spine — retain both package and embedded Spine runtime license notices. Spine usage is subject to the Spine Editor/runtime licensing terms included with the runtime.
- vis-timeline / vis-graph2d 8.5.2 — MIT or Apache-2.0 — https://github.com/visjs/vis-timeline

PixiJS, Spine 3.8 and vis assets reuse the identical pinned files from this tool's CocosCreator38Extension/static/vendor. Spine 4.0 and 4.1 come from the version-pinned jsDelivr npm distributions. The standalone page references these local files and does not fetch a moving CDN version at launch.

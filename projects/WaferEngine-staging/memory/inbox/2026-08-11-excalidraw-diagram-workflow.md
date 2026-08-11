Situation: Non-data figures such as architecture diagrams and timelines were
being treated as ad-hoc SVG/PPTX output, making human edits and later agent
updates difficult to coordinate.

Decision: The shared `excalidraw-diagrams` skill is now the default workflow for
non-data diagrams in both Claude Code and Codex. The `.excalidraw` file is the
source of truth; SVG/PNG are derived exports. `wafer-slides` invokes the diagram
skill for non-data figures and consumes the export through its `figure`
archetype. Matplotlib/seaborn remains the route for experimental/computed data
plots.

Collaboration procedure: Agent reads and patches the current source, human
edits the same source in an Excalidraw-compatible editor, then the next agent
turn reloads the saved source before applying a minimal patch. For a remote
canvas, expose the gala2 service to the Mac through an SSH port forward rather
than maintaining a silent second copy.

Manual-edit mode: when the user asks to edit the document by hand, the skill
may start/check the remote service, provide the Mac tunnel command and browser
URL, then wait for the user to finish before reloading and exporting. The agent
cannot create the Mac-side GUI/tunnel while it runs on gala2. The recommended
direct editor is the VS Code `pomdtr.excalidraw-editor` extension; Cursor can
try the same VS Code extension model, with browser editing as fallback.

Status: captured
Promotion: procedural; the shared skill was created under `~/claude-skills`.

# Architecture viewer

[Open the interactive diagram](https://jjuck.github.io/agent-context-substrate/site/).

`index.html` is the standalone Archify viewer. `preview.png` is the README thumbnail. The viewer needs no API server, credentials, or build step. Authored labels are Korean; the fixed viewer controls are English.

The diagram is pinned to source revision `ea83152d01dccecf359164971de8e592cad577f3`; source links intentionally remain pinned. [provenance.json](provenance.json) records the HTML digest and generation checks. A documentation edit does not imply that the diagram has been regenerated.

## Update and publish

1. Review the changed runtime flow against source, then regenerate with the Archify skill when the architecture changes.
2. Run Archify showcase finalization, strict artifact checking and browser checking. Review the preview and update the HTML, thumbnail and provenance together.
3. Check local Markdown links and `git diff --check`; commit the static files.
4. GitHub Pages publishes **`main` → `/docs`**. The root landing page redirects to `site/`; no preview branch or custom Actions workflow is required.
5. Verify the deployed page and node source links after the Pages build completes.

Do not publish session exports, local configuration, credentials, or generator receipts containing local absolute paths.

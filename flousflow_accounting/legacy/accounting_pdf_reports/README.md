# Accounting PDF Reports — PDF renderer prerequisite

Odoo renders this addon's QWeb reports as HTML and uses `wkhtmltopdf` to
produce PDF files. The renderer must be installed on the Odoo server host; it
is not installed by pip and is not bundled in this addon because it is a
platform-specific executable.

## Supported renderer

Use the Odoo-compatible `wkhtmltopdf` 0.12.6 build with patched Qt. Odoo's
[Odoo 20 source installation guide](https://www.odoo.com/documentation/20.0/administration/on_premise/source.html)
requires manual installation of this version for report headers and footers.
The upstream project hosts its macOS package in the
[0.12.6-2 macOS release](https://github.com/wkhtmltopdf/packaging/releases/tag/0.12.6-2).

## Install and verify

1. Install the compatible package for the operating system and architecture of
   the machine running Odoo. On macOS, the upstream 0.12.6-2 package contains
   an x86_64 binary. Apple Silicon machines need Rosetta 2 installed first;
   install Rosetta through macOS and follow its license prompt before running
   the upstream package.
2. Confirm the renderer is on the Odoo service user's `PATH` and reports the
   patched Qt build:

   ```sh
   command -v wkhtmltopdf
   wkhtmltopdf --version
   ```

   The version output should include `0.12.6` and `with patched qt`.
3. Restart the Odoo process after installing or changing the renderer so Odoo
   refreshes its cached renderer status.
4. Print a report from Odoo and confirm the result is a PDF, not the HTML
   fallback message.

If `wkhtmltopdf` is absent, Odoo can still display the HTML report, but PDF
printing is unavailable until the host dependency is installed and detected.

# SourceTable installed dependency notice inventory

Captured from the validated Linux arm64 product image on 2026-10-10. This inventory records package metadata and included notice paths; it is not a dependency-wide licensing approval. Runtime versions are pinned in the product lock, with the immutable tested image ID in the v1 manifest. The base image also includes pip, which appears here.

Both source distributions contain their MIT notices. PDFium includes additional native/build notices, and text-unidecode declares Artistic/GPL alternatives. These require their own distribution review; a top-level MIT source license does not describe every installed component. No notices were removed or modified.

| Installed package | Version | Declared expression/classifiers | Included notice files |
| --- | --- | --- | --- |
| [annotated-doc](https://github.com/fastapi/annotated-doc) | 0.0.5 | MIT | `annotated_doc-0.0.5.dist-info/licenses/LICENSE` |
| [annotated-types](https://github.com/annotated-types/annotated-types) | 0.8.0 | MIT | `annotated_types-0.8.0.dist-info/licenses/LICENSE` |
| [attrs](https://www.attrs.org/) | 26.1.0 | MIT | `attrs-26.1.0.dist-info/licenses/LICENSE` |
| [certifi](https://github.com/certifi/python-certifi) | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | `certifi-2026.7.22.dist-info/licenses/LICENSE` |
| [cffi](https://cffi.readthedocs.io/) | 2.1.1 | MIT-0 | `cffi-2.1.1.dist-info/licenses/LICENSE` |
| [chardet](https://github.com/chardet/chardet) | 7.6.0 | 0BSD | `chardet-7.6.0.dist-info/licenses/LICENSE` |
| [charset-normalizer](https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md) | 3.5.2 | No SPDX expression/classifier in captured metadata | `charset_normalizer-3.5.2.dist-info/licenses/LICENSE` |
| [cryptography](https://cryptography.io/en/latest/changelog/) | 50.0.2 | Apache-2.0 OR BSD-3-Clause | `cryptography-50.0.2.dist-info/licenses/LICENSE`; `cryptography-50.0.2.dist-info/licenses/LICENSE.APACHE`; 1 additional bundled notices |
| [frictionless](https://github.com/frictionlessdata/frictionless-py) | 5.20.0 | MIT | `frictionless-5.20.0.dist-info/licenses/AUTHORS.md`; `frictionless-5.20.0.dist-info/licenses/LICENSE.md` |
| [humanize](https://github.com/python-humanize/humanize/issues) | 4.16.0 | MIT | `humanize-4.16.0.dist-info/licenses/LICENCE` |
| [idna](https://github.com/kjd/idna/blob/master/HISTORY.md) | 3.20 | BSD-3-Clause | `idna-3.20.dist-info/licenses/LICENSE.md` |
| [isodate](https://github.com/gweis/isodate/) | 0.7.2 | BSD License | `isodate-0.7.2.dist-info/LICENSE` |
| [Jinja2](https://jinja.palletsprojects.com/changes/) | 3.1.6 | BSD License | `jinja2-3.1.6.dist-info/licenses/LICENSE.txt` |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT | `jsonschema-4.26.0.dist-info/licenses/COPYING` |
| [jsonschema-specifications](https://jsonschema-specifications.readthedocs.io/) | 2025.9.1 | MIT | `jsonschema_specifications-2025.9.1.dist-info/licenses/COPYING` |
| [markdown-it-py](https://markdown-it-py.readthedocs.io) | 4.2.0 | MIT License | `markdown_it_py-4.2.0.dist-info/licenses/LICENSE`; `markdown_it_py-4.2.0.dist-info/licenses/LICENSE.markdown-it` |
| [marko](https://github.com/frostming/marko) | 2.2.4 | No SPDX expression/classifier in captured metadata | `marko-2.2.4.dist-info/licenses/LICENSE` |
| [MarkupSafe](https://palletsprojects.com/donate) | 3.0.4 | BSD-3-Clause | `markupsafe-3.0.4.dist-info/licenses/LICENSE.txt` |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT License | `mdurl-0.1.2.dist-info/LICENSE` |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | 20260107 | MIT | `pdfminer_six-20260107.dist-info/licenses/LICENSE` |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.10 | MIT License | `pdfplumber-0.11.10.dist-info/licenses/LICENSE.txt` |
| [petl](https://github.com/petl-developers/petl) | 1.7.28 | MIT License | `petl-1.7.28.dist-info/licenses/LICENSE.txt` |
| [pillow](https://pillow.readthedocs.io/en/stable/releasenotes/index.html) | 12.3.0 | MIT-CMU | `pillow-12.3.0.dist-info/licenses/LICENSE` |
| [pip](https://pip.pypa.io/) | 25.0.1 | MIT License | `pip-25.0.1.dist-info/LICENSE.txt`; `pip/_vendor/packaging/licenses/__init__.py`; 1 additional bundled notices |
| [pycparser](https://github.com/eliben/pycparser) | 3.11 | BSD-3-Clause | `pycparser-3.11.dist-info/licenses/LICENSE` |
| [pydantic](https://github.com/pydantic/pydantic) | 2.14.0 | MIT | `pydantic-2.14.0.dist-info/licenses/LICENSE` |
| [pydantic_core](https://github.com/sponsors/samuelcolvin) | 2.50.0 | MIT | `pydantic_core-2.50.0.dist-info/licenses/LICENSE` |
| [Pygments](https://pygments.org) | 2.21.0 | BSD-2-Clause | `pygments-2.21.0.dist-info/licenses/AUTHORS`; `pygments-2.21.0.dist-info/licenses/LICENSE` |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | 5.14.0 | No SPDX expression/classifier in captured metadata | `pypdfium2-5.14.0.dist-info/licenses/LICENSES/Apache-2.0.txt`; `pypdfium2-5.14.0.dist-info/licenses/LICENSES/BSD-3-Clause.txt`; 16 additional bundled notices |
| [python-dateutil](https://dateutil.readthedocs.io/en/stable/) | 2.9.0.post0 | BSD License; Apache Software License | `python_dateutil-2.9.0.post0.dist-info/LICENSE` |
| [python-slugify](https://github.com/un33k/python-slugify) | 9.1.3 | MIT | `python_slugify-9.1.3.dist-info/licenses/LICENSE` |
| [PyYAML](https://github.com/yaml/pyyaml/issues) | 6.0.3 | MIT License | `pyyaml-6.0.3.dist-info/licenses/LICENSE` |
| [referencing](https://referencing.readthedocs.io/) | 0.37.0 | MIT | `referencing-0.37.0.dist-info/licenses/COPYING` |
| [requests](https://requests.readthedocs.io) | 2.34.2 | Apache Software License | `requests-2.34.2.dist-info/licenses/LICENSE`; `requests-2.34.2.dist-info/licenses/NOTICE` |
| [rfc3986](http://rfc3986.readthedocs.io) | 2.0.0 | Apache Software License | `rfc3986-2.0.0.dist-info/LICENSE` |
| [rich](https://rich.readthedocs.io/en/latest/) | 15.0.0 | MIT License | `rich-15.0.0.dist-info/licenses/LICENSE` |
| [rpds-py](https://rpds.readthedocs.io/) | 2026.9.1 | MIT | `rpds_py-2026.9.1.dist-info/licenses/LICENSE` |
| [shellingham](https://github.com/sarugaku/shellingham) | 1.5.4 | ISC License (ISCL) | `shellingham-1.5.4.dist-info/LICENSE` |
| [simpleeval](https://github.com/danthedeckie/simpleeval) | 1.0.8 | MIT License | `simpleeval-1.0.8.dist-info/licenses/LICENCE` |
| [six](https://github.com/benjaminp/six) | 1.17.0 | MIT License | `six-1.17.0.dist-info/LICENSE` |
| [tabulate](https://github.com/astanin/python-tabulate) | 0.10.0 | MIT | `tabulate-0.10.0.dist-info/licenses/LICENSE` |
| [text-unidecode](https://github.com/kmike/text-unidecode/) | 1.3 | Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+) | `text_unidecode-1.3.dist-info/LICENSE.txt` |
| [typer](https://github.com/fastapi/typer) | 0.27.3 | MIT | `typer-0.27.3.dist-info/licenses/LICENSE`; `typer/_click/LICENSE.txt` |
| [typing-inspection](https://github.com/pydantic/typing-inspection) | 0.4.4 | MIT | `typing_inspection-0.4.4.dist-info/licenses/LICENSE` |
| [typing_extensions](https://github.com/python/typing_extensions/issues) | 4.16.0 | PSF-2.0 | `typing_extensions-4.16.0.dist-info/licenses/LICENSE` |
| [urllib3](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) | 2.8.0 | MIT | `urllib3-2.8.0.dist-info/licenses/LICENSE.txt` |
| [validators](https://python-validators.github.io/validators) | 0.35.0 | MIT License | `validators-0.35.0.dist-info/licenses/LICENSE.txt` |

Full installed metadata and all bundled paths are retained locally under ignored `artifacts/product-license-inventory.json`; package notices remain inside the image. This is a package inventory, not a complete OS/base-image software bill of materials. Preserve/review applicable notices when distributing the image and review source changes before a later version.

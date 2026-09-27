# Crystal Structure Explorer

An interactive educational web application for exploring Simple Cubic (SC), Body-Centred Cubic (BCC), Face-Centred Cubic (FCC), and Hexagonal Close-Packed (HCP) structures. Python supplies the scientific calculations and crystallographic geometry; the browser visualizes that data with locally served Three.js.

## Features

- Interactive 3D Explorer with live lattice parameters, cubic supercells, and HCP basal-plane prism clusters.
- Four views: Crystal, Unit Cell, Coordination, and Stacking. Unit Cell uses solid capped hard-sphere cuts; stacking separation is visual only.
- Cited elemental presets: α-Polonium, α-Iron, Copper, and Magnesium, with calculated theoretical density and scientific properties.
- Lattice-site selection and coordinate inspection in Crystal, Coordination, and Stacking; selection is intentionally disabled in Unit Cell.
- Crystallographic axes, cell lines, contact diagonals, coordination guides, reset view, native fullscreen, and reduced-motion-aware auto-rotation.
- Responsive desktop, tablet, and phone layouts, touch orbit/zoom, and accessible compact navigation.
- Side-by-side interactive comparison, scientific documentation, and academic project information.

## Technology

Python 3.14, NumPy, Flask, Gunicorn, HTML, CSS, vanilla JavaScript, Three.js, KaTeX, and pytest. No frontend package manager or build step is required.

Three.js **r186 (0.186.0)** and KaTeX **0.18.7** are vendored locally with their licenses under `static/vendor/`. Their JavaScript, styles, and fonts do not require a CDN. Material records and citations are stored locally in `data/materials.json`; application startup does not fetch external material data. Third-party licenses are preserved; no license has yet been selected for the project itself.

## Project Structure

```text
.
├── app.py                       # Flask pages, API, health check, error handling
├── crystal_model.py             # Scientific calculations and display geometry
├── visualization_geometry.py    # Mode-specific crystallographic geometry
├── comparison_data.py           # Shared scientific comparison presentation
├── data/                        # Material catalog and academic project metadata
├── templates/                   # Shared layout, four pages, error pages
├── static/
│   ├── css/                     # Shared responsive styling
│   ├── js/                      # Explorer, comparison viewers, math, navigation
│   ├── images/team/             # Local team portraits
│   └── vendor/                  # Three.js, OrbitControls, KaTeX, licenses
├── tests/                       # Scientific, API, page, and integrity tests
├── requirements.txt             # Pinned runtime dependencies
├── requirements-dev.txt         # Runtime dependencies plus pytest
├── .python-version              # Python 3.14 runtime selection
└── render.yaml                  # Minimal Render web-service configuration
```

## Local Setup

Use Python **3.14**. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

If a working `.venv` already exists, reuse it instead of recreating it. Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/). Without activating the environment, launch with:

```bash
.venv/bin/python app.py
```

Debugging is off by default. For local development only, opt in with `CRYSTAL_DEBUG=1 python app.py`. Do not enable debug mode in production. No secrets, database, or `.env` file are required.

## Tests

With the environment activated:

```bash
pytest
python -m pip check
```

Or run the suite directly:

```bash
.venv/bin/python -m pytest
```

## Pages and API

| Path | Purpose |
| --- | --- |
| `/` | Interactive Explorer |
| `/compare` | Four interactive comparison models and a scientific comparison table |
| `/docs` | Usage, physics, conventions, citations, and limitations |
| `/about` | Academic context, coursework connections, and team |
| `/health` | Lightweight JSON health check |
| `/api/materials` | Validated local material catalog |
| `/api/structure` | Calculated structure, scientific positions, display sites, and visualization geometry |

`GET /api/structure` requires `structure` (`sc`, `bcc`, `fcc`, or `hcp`) and positive finite `a` in ångströms. Optional parameters are `size` (1–4, default 1), `view` (`crystal`, `unit`, `coordination`, or `stacking`), and compatible `material` ID. HCP additionally accepts `c_over_a` (ideal ratio by default) and `display_size` (1–4 basal-plane prisms per direction, default 1). The HCP display size is independent of the primitive scientific supercell size. Cubic structures ignore HCP-only parameters. Invalid input returns a safe JSON error with HTTP 400.

Examples, relative to the application host:

```text
/api/structure?structure=fcc&a=3&size=2
/api/structure?structure=hcp&a=3&size=1&display_size=2
/api/structure?structure=fcc&a=3.6148&material=copper&view=coordination
```

### Scientific conventions

Lattice vectors are NumPy matrix rows; lattice coordinates convert as `cartesian = fractional @ lattice_vectors`. API coordinates remain unchanged by visual centering, HCP presentation rotation, or layer separation.

Periodic scientific `supercell` positions and finite educational `display` sites are distinct. For example, SC `size=3` contains 27 generated basis positions but displays 64 lattice sites to close all three cell intervals per direction. HCP retains a **2-atom primitive basis** with 120° basal vectors; one educational prism has **6 effective atoms** and **17 visible sites**. HCP display clusters repeat in the basal plane and remain one prism high, not an N × N × N primitive supercell.

Non-ideal HCP packing uses the shortest geometric separation; the standard coordination number 12 describes ideal HCP. Material density is calculated from the cited molar mass and scientific cell volume, not assigned to a structure universally. α-Polonium uses the Po-209 isotope mass as a representative density input, not a standard atomic weight. Detailed qualifications and sources are in `/docs` and the local catalog.

## Production Server

Gunicorn imports the Flask application without starting the development server:

```bash
gunicorn app:app
```

For a local production smoke test:

```bash
.venv/bin/gunicorn --bind 127.0.0.1:8000 app:app
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Gunicorn targets Unix-like systems, including macOS and Linux. Run production commands from the repository root.

## Deployment on Render

The repository includes `render.yaml` for one Python web service and `.python-version` selecting **3.14** (Render selects the corresponding supported patch). After creating an empty GitHub repository and pushing `main`, connect that repository to Render through a Blueprint or create a web service with these settings:

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Branch | `main` |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn app:app` |
| Health check | `/health` |
| Auto-deploy | On commits to the linked branch |

Gunicorn uses Render's supplied `PORT`; no Render-specific Flask development-server configuration is needed. Do not enable Flask debugging. There are no credentials, disks, background workers, or databases to configure. The repository is prepared for deployment but no live URL is assumed.

Configuration follows Render's [Flask deployment guide](https://render.com/docs/deploy-flask), [Blueprint reference](https://render.com/docs/blueprint-spec), and [Python version guide](https://render.com/docs/python-version).

## Academic Context

Developed for **B.Sc. Physics, Semester 5**, **Solid State Physics (24SPT-301)** at **Chandigarh University**, under the assigned title *3D Interactive SC-BCC-FCC-HCP Crystal Structure Model*.

Team: **Dhiman Das — 24BSP70022** and **Tanmay Sharma — 24BSP70007**. Submitted to **Dr. Sumit Bhardwaj**. The About page contains the full academic presentation and acknowledgement of implementation assistance from OpenAI Codex.

# Batcomputer Website

This repository's website entry point is:

- `index.html` (redirects to `batcomputer_console.html`)

For GitHub Pages, publish this repository and GitHub will load `index.html` automatically.

## Local run

```powershell
python -m pip install -r requirements.txt
python app.py
```

The Flask server provides the HUD pages, Alfred chat endpoint, and proposal workflow endpoints.

## Website architecture

- `app.py` owns routing, static assets, Alfred responses, health, project inventory, and proposal state.
- `batcomputer_console.html` and `app.js` provide the homepage HUD, panels, chat, voice input, and speech output.
- `alfred_agent_console.html` and `alfred_agent.js` provide proposal review and explicit approval controls.
- Category HTML files describe software, cybersecurity, IT support, and network work.
- `projects/` contains the individual project detail pages.
- `style.css` supplies the shared HUD visual system.

## Website features

- Responsive portfolio HUD with category and project navigation.
- Alfred responses for greetings, status, capabilities, and technical focus areas.
- Browser voice input and speech synthesis when supported by the browser.
- Explicit approve/reject controls for code and website redesign proposals.
- Runtime endpoints at `/api/health` and `/api/site/summary`.
- Safe local previews constrained to this Website directory.

## Current scope and roadmap

The current Alfred server is deterministic and local. Proposal approval returns reviewed content but does not write files automatically. The next upgrade is connecting a bounded local model for actual project-specific analysis and code generation, followed by persistent proposal state and automated browser smoke tests.

Add the canonical GitHub repository URL here when this Website project is published.

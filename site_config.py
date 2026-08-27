import os
from pathlib import Path
from urllib.parse import quote, urlsplit

REPOSITORY_URL = "https://github.com/grey-ghost-1/Batcomputer-Portfolio"
SOURCE_REF = "agents/batcomputer-website-query"
PUBLIC_SOURCE_PATHS = (
    "",
    "platform",
    "orbital-data-lab",
    "algorithms-quality",
    "algorithms-quality/QUALITY.md",
    "alfred-assistant",
    "ALFRED_STATUS.md",
    ".github/workflows/ci.yml",
)


def _https_url(value):
    value = value.strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value


def _public_source_url(value):
    url = _https_url(value)
    if not url or "\\" in url:
        return None
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment or "%" in parsed.path:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.hostname != "github.com"
        or port not in {None, 443}
        or len(parts) != 4
        or parts[2] != "tree"
        or any(part in {".", ".."} for part in parts)
    ):
        return None
    return url.rstrip("/")


def _public_source_urls(base_url):
    return {
        path: (
            base_url
            if not path
            else f"{base_url}/{'/'.join(quote(part, safe='') for part in path.split('/'))}"
        )
        for path in PUBLIC_SOURCE_PATHS
    }


def _email(value):
    value = value.strip()
    if (
        not value
        or any(character.isspace() for character in value)
        or value.count("@") != 1
        or value.startswith("@")
        or value.endswith("@")
    ):
        return None
    return value


def _resume_path(value, base_dir):
    value = value.strip().replace("\\", "/")
    if not value or "\x00" in value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or candidate.suffix.lower() != ".pdf":
        return None
    resolved = (base_dir / candidate).resolve()
    try:
        relative = resolved.relative_to(base_dir)
    except ValueError:
        return None
    if len(relative.parts) < 2 or relative.parts[0] != "assets" or not resolved.is_file():
        return None
    return relative.as_posix()


def public_site_config(base_dir, environ=None):
    environment = os.environ if environ is None else environ
    optional_links = []

    email = _email(environment.get("SITE_CONTACT_EMAIL", ""))
    if email:
        optional_links.append({"label": "Email", "href": f"mailto:{email}", "kind": "email"})

    linkedin = _https_url(environment.get("SITE_LINKEDIN_URL", ""))
    if linkedin:
        optional_links.append({"label": "LinkedIn", "href": linkedin, "kind": "linkedin"})

    resume = _resume_path(environment.get("SITE_RESUME_PATH", ""), Path(base_dir).resolve())
    if resume:
        optional_links.append({"label": "Resume", "href": resume, "kind": "resume"})

    demos = {}
    for key, variable in (
        ("platform", "SITE_PLATFORM_DEMO_URL"),
        ("orbital", "SITE_ORBITAL_DEMO_URL"),
    ):
        url = _https_url(environment.get(variable, ""))
        if url:
            demos[key] = url

    config = {
        "repository_url": REPOSITORY_URL,
        "source_ref": SOURCE_REF,
        "optional_links": optional_links,
        "demos": demos,
    }
    public_source_url = _public_source_url(environment.get("SITE_PUBLIC_SOURCE_URL", ""))
    if public_source_url:
        config["public_source_urls"] = _public_source_urls(public_source_url)
    return config

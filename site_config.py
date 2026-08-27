import os
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY_URL = "https://github.com/grey-ghost-1/Batcomputer-Portfolio"
SOURCE_REF = "grey-ghost-1-recruiter-ready-portfolio"


def _https_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value


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

    return {
        "repository_url": REPOSITORY_URL,
        "source_ref": SOURCE_REF,
        "optional_links": optional_links,
        "demos": demos,
    }

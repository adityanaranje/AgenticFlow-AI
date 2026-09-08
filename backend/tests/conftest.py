"""Shared pytest fixtures for AgentFlow AI tests."""

import base64
import os
import sys

import pytest

# Ensure the backend package is importable regardless of cwd.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _unconfigured_services() -> None:
    """Reset process settings so external services appear offline.

    Running tests must never require a live Supabase / Qdrant / OpenAI /
    Redis / Langfuse. Any module creating such a client gets the "not
    configured" branch (returns None) instead.
    """
    env = os.environ
    for var in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "OPENAI_API_KEY",
        "REDIS_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        env.pop(var, None)


_unconfigured_services()


@pytest.fixture(autouse=True)
def _ensure_services_unconfigured():
    _unconfigured_services()
    from app.core import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture
def sample_txt():
    return (
        "AgentFlow AI is a multi-tenant research platform.\n\n"
        "Organizations upload documents and run agentic research.\n\n"
        "Tenant isolation prevents users from seeing other organizations' data.\n\n"
        "Row level security and backend authorization are the security boundary.\n\n"
    ) * 20


# A real 2-page PDF (generated once; bytes are stable). pypdf extracts
# text from it without needing reportlab at test runtime.
_SAMPLE_PDF_B64 = (
    "JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDggMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCA3IDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9Db250ZW50cyA5IDAgUiAvTWVkaWFCb3ggWyAwIDAgNjEyIDc5MiBdIC9QYXJlbnQgNyAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNSAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDcgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDkwODE4MDU1NCswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDkwODE4MDU1NCswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago3IDAgb2JqCjw8Ci9Db3VudCAyIC9LaWRzIFsgMyAwIFIgNCAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjggMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjU1Cj4+CnN0cmVhbQpHYXQmSVltUz8lJ0V1az5ZSUw+Z2VAbWJWbTklMiIva1VTY1BaMCxMLlxUPC9IXDhuY29ZRGFxT0g9Z0RiOU9yNmRKSV9haSpgZGkjYyhqM09IKTBBI3RNPC9uKz9SSVgwPyokIVVLO2toLE8oLSIvVSdbaDtfdTVVUnNGdTJqaXVeL2g5LHJvM0QxN3FZbD5bRjEjZXAmQTs8Kk5kXzZtTW5yMCZDQ2oiWjtRXztZMGlHVEw4O2BQOlAiNW0oV0QiTE03TnReaWwqP05oVTtldVliIWg8UU4wSy87aF9VRTIyLXF0NywmM1g4K1x0WmZqP0hTJ2VJKyFdK1Rxfj5lbmRzdHJlYW0KZW5kb2JqCjkgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTYxCj4+CnN0cmVhbQpHYXJXMFltdUBOJjRDbFpAUzNvQD49KWU7VShyQSpxWkBkVCJVb1RGNDlGTDFcWXQ0OVJFNi1yMUlFaWZvWmwiZyhXUF0vVEclLyY8Q0kob0VUSmBrcUd0cFJaMm0kLG1hPFFIMjUiJFVLQzxqTSc3Ql42MFY6WSs7PD9AJSY4dSEiZDRuPGlySldeTSwzITFoaVhoJD8sQGlsYUJJXiJ+PmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDEwCjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA2MSAwMDAwMCBuIAowMDAwMDAwMDkyIDAwMDAwIG4gCjAwMDAwMDAxOTkgMDAwMDAgbiAKMDAwMDAwMDM5MiAwMDAwMCBuIAowMDAwMDAwNTg1IDAwMDAwIG4gCjAwMDAwMDA2NTMgMDAwMDAgbiAKMDAwMDAwMDkxNCAwMDAwMCBuIAowMDAwMDAwOTc5IDAwMDAwIG4gCjAwMDAwMDEzMjQgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8MzI5Mzc0MDkyYTRiNTExZjc0NjNhNmIzMjBmM2E4ZjM+PDMyOTM3NDA5MmE0YjUxMWY3NDYzYTZiMzIwZjNhOGYzPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA2IDAgUgovUm9vdCA1IDAgUgovU2l6ZSAxMAo+PgpzdGFydHhyZWYKMTU3NQolJUVPRgo="
)


@pytest.fixture
def sample_pdf_bytes():
    return base64.b64decode(_SAMPLE_PDF_B64)

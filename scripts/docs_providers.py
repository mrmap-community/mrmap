#!/usr/bin/env python3
"""The model-provider interface of the documentation pipeline (#1598, epic #1589).

One narrow contract, four rules, and an adapter test suite that every adapter has
to pass unchanged (ADR-0001 sections 9 and 8; validation row V-15). Everything
about "provider independence" in this pipeline is a consequence of those rules, so
they live here as code and are asserted there as checks rather than written down as
intent somewhere nobody executes.

The rules:

1. **An adapter that cannot report ``model_id`` and ``usage`` cannot be used.**
   Provenance (section 4) and the token budget (section 8) both read those fields,
   so an adapter that omits them would make the run unauditable rather than
   merely less precise. ``describe()`` has to say it reports them, and the contract
   suite proves it by driving a request and reading the numbers.
2. **Every citation must name a fact the request carried.** Enforced in
   :func:`validate_response` against the request, not against the adapter's own
   account of itself, so a compromised or buggy adapter cannot widen its own
   permission. A response citing an unknown fact is discarded in full.
3. **A refusal is a valid response.** ``refusal_reason`` set and no text means the
   topic is reported *unsupported* - never guessed at. An adapter that cannot
   refuse (returns prose instead of declining) is rejected by the suite, because
   "unsupported" is the single most important behaviour of the whole epic.
4. **Adding a vendor means adding an adapter and running the same suite.** No
   prompt, page or gate changes; the suite is :func:`adapter_contract_checks`,
   which the CLI can run against any configured adapter.

Three adapters ship here, and they are chosen to be genuinely different shapes
rather than three spellings of one:

``fake``     deterministic, offline, no credentials, no network. The default, and
             what CI uses. It writes no prose of its own: it composes sentences
             from the facts it was given, which is the correct behaviour for a
             component whose job is to be replaced.
``command``  runs an allowlisted local binary that speaks the request/response
             JSON pair on stdin/stdout. This is the shape an operator reaches for
             when their model is a CLI, and the shape a suite reaches for when it
             needs to prove argv construction, timeouts and a hostile child.
``http``     POSTs the request to one configured endpoint. One URL, no redirects,
             no ambient credentials - the endpoint is the only network address a
             documentation run may reach, and the secret arrives through the
             environment, never through the request body or a log.

A fourth shape the issue mentions and this module deliberately does **not**
implement is "call the vendor SDK". The epic asks for a minimal compatible adapter
rather than a vendor dependency; the ``command`` adapter is how an SDK-backed
wrapper attaches, and keeping the pipeline's dependency set at the standard
library is what lets the required path run on a clean runner.
"""

from __future__ import annotations

import abc
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402

MAX_RESPONSE_CHARS = 20_000
#: Rough enough to be honest: a token is not four characters, but a budget that
#: pretends to know a vendor's tokenizer is pretending. The number exists to stop
#: a runaway generation, and the suite proves the stop happens.
CHARS_PER_TOKEN = 4
UNAVAILABLE_MARKERS = ("unavailable", "timeout", "timed out", "refused",
                       "503", "502", "504", "no route", "connection reset",
                       "could not start", "not found")


class ProviderError(RuntimeError):
    """The provider is unavailable or answered with something unusable.

    Distinct from a refusal: "the model is down" fails the run (fail-closed, so
    the previous publication stands), while "the model declines this topic" is a
    reportable outcome that leaves the rest of the run intact.
    """


class AdapterPolicyError(ProviderError):
    """An adapter that does not meet the contract's preconditions."""


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def build_request(*, claim_id: str, kind: str, audience: str, locale: str,
                  facts, evidence_refs=(), style_profile=None, budget=None,
                  prior_prose: str | None = None) -> dict:
    """The request object a provider receives - the whole prompt boundary.

    Facts and evidence digests only. No file content, no fetched document, no
    instruction from a page: whatever a prompt-injected README says, it never
    reaches an adapter as anything other than a digest.
    """
    request = {
        "schema": contract.REQUEST_SCHEMA,
        "claim_id": claim_id,
        "kind": kind,
        "audience": audience,
        "locale": locale,
        "facts": [dict(fact) for fact in facts],
        "evidence_refs": list(evidence_refs),
        "style_profile": dict(style_profile or DEFAULT_STYLE_PROFILE),
        "budget": dict(budget or {}),
        "prior_prose": prior_prose,
    }
    contract.require_valid("request", request)
    return request


DEFAULT_STYLE_PROFILE = {
    "voice": "third person, present tense, no marketing",
    "sentence_limit": 12,
    "must_name_only_cited_facts": True,
    "headings": "markdown level 2 and 3 only",
    "forbid": ["we", "our", "simply", "easy", "obviously"],
}


def validate_response(response, request) -> list[contract.Issue]:
    """Judge one response against the request it answers.

    Returns the issues; empty means renderable. This is the mechanical form of
    "no invented features", and it is adapter-independent on purpose: it reads the
    response as data, never as an instruction, so it cannot be argued out of
    existing by a provider's own metadata.
    """
    issues = list(contract.errors(contract.validate("response", response)))
    if issues:
        return issues
    known = {fact["id"] for fact in request["facts"]}
    cited = response["cited_fact_ids"]
    if response["refusal_reason"] is not None:
        if response["text"]:
            issues.append(contract.Issue("text",
                                         "a refusal must carry no text"))
        return issues
    unknown = sorted(set(cited) - known)
    if unknown:
        issues.append(contract.Issue(
            "cited_fact_ids",
            f"cites {len(unknown)} fact(s) the request did not carry: "
            + ", ".join(unknown[:5])))
    if not cited:
        issues.append(contract.Issue("cited_fact_ids",
                                     "prose without a citation is not published"))
    if not response["text"].strip():
        issues.append(contract.Issue("text",
                                     "no text and no refusal: nothing to publish"))
    if len(response["text"]) > MAX_RESPONSE_CHARS:
        issues.append(contract.Issue("text",
                                     f"longer than {MAX_RESPONSE_CHARS} characters"))
    # The identifiers the prose names must be identifiers the facts carry. A model
    # that invents `WebMapServiceUpdateSettingPro` is caught here rather than by a
    # reader, which is the difference between a gate and a hope.
    invented = invented_identifiers(response["text"], request)
    if invented:
        issues.append(contract.Issue(
            "text", "names identifiers no fact carries: "
            + ", ".join(sorted(set(invented))[:6])))
    usage = response["usage"]
    if usage["prompt_tokens"] < 0 or usage["completion_tokens"] < 0:
        issues.append(contract.Issue("usage", "negative token counts"))
    return issues


IDENTIFIER_RE = re.compile(r"\b(?:[A-Z][a-z0-9]*){2,}\b")


def invented_identifiers(text: str, request) -> list[str]:
    """CamelCase names in the prose that appear in none of the facts.

    Deliberately narrow: only CamelCase, because that is the shape MrMap's own
    identifiers have and the shape an invented feature name takes. Lowercase prose
    is not policed here - it is the wording the reviewer reads, not the claim.
    """
    allowed = set()
    for fact in request["facts"]:
        allowed.add(fact["name"])
        for field in fact.get("fields", ()):
            allowed.update(IDENTIFIER_RE.findall(str(field)))
        allowed.update(IDENTIFIER_RE.findall(str(fact.get("value") or "")))
        allowed.update(IDENTIFIER_RE.findall(str(fact.get("help") or "")))
        extra = fact.get("extra") or {}
        for value in extra.values():
            allowed.update(IDENTIFIER_RE.findall(str(value)))
    return [name for name in IDENTIFIER_RE.findall(text) if name not in allowed]


class ProviderAdapter(abc.ABC):
    """The one interface the author uses. Nothing else in the system knows a model exists."""

    name: str = "abstract"
    reports_usage = False
    supports_refusal = False
    requires_credentials = False
    is_networked = False

    def __init__(self, *, model_id: str | None = None, workspace=None):
        if not contract.MODEL_REF_RE.fullmatch(model_id or ""):
            raise AdapterPolicyError(
                f"{self.name}: model_id must be a prefixed label matching "
                f"{contract.MODEL_REF_RE.pattern}, got {model_id!r}. An adapter "
                "that cannot say which model answered cannot be used.")
        self.model_id = model_id
        self.workspace = workspace
        self.calls: list[dict] = []

    # -- introspection ---------------------------------------------------------
    def describe(self) -> dict:
        return contract.provider_info(
            provider=self.name, model_id=self.model_id,
            reports_usage=self.reports_usage,
            supports_refusal=self.supports_refusal,
            requires_credentials=self.requires_credentials,
            is_networked=self.is_networked)

    def healthcheck(self) -> tuple[bool, str]:
        """Cheap readiness probe. A run that can reach no provider fails early."""
        return True, "no probe needed"

    # -- the call --------------------------------------------------------------
    def generate(self, request: dict) -> dict:
        """Answer one request, or raise :class:`ProviderError`.

        Wraps :meth:`_generate` with the checks that must not be skippable by an
        adapter: the response is schema-validated and usage-reported before the
        caller sees it, so a subclass cannot quietly return a dict that would make
        the run unauditable.
        """
        contract.require_valid("request", request)
        started = time.monotonic()
        response = self._generate(request)
        response.setdefault("schema", contract.RESPONSE_SCHEMA)
        response.setdefault("provider", self.name)
        response["model_id"] = self.model_id
        if self.reports_usage:
            usage = response.get("usage") or {}
            if usage.get("prompt_tokens") is None or \
                    usage.get("completion_tokens") is None:
                raise ProviderError(
                    f"{self.name}: adapter declares reports_usage but returned no "
                    "usage; an adapter that cannot report tokens cannot be used")
        else:
            raise AdapterPolicyError(
                f"{self.name}: adapters must report usage; see ADR-0001 section 9")
        self.calls.append({"request": request, "response": response,
                           "duration_s": round(time.monotonic() - started, 3)})
        return response

    @abc.abstractmethod
    def _generate(self, request: dict) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError


class FakeAdapter(ProviderAdapter):
    """Deterministic, offline, credential-free stand-in for a real model.

    It composes sentences out of the facts it was handed and cites each one. That
    is not a toy: the pipeline's job is to refuse un-evidenced prose, so the test
    double must produce *evidenced* prose and nothing else. Scripted behaviours
    (malformed output, refusal, unavailability, token inflation) are constructor
    arguments, which is how the suites reach "unavailable model", "malformed
    output" and "budget exhausted" without a network or a credential.
    """

    name = "fake"
    reports_usage = True
    supports_refusal = True

    def __init__(self, *, model_id: str = "mrmap-docs-model/fake-1",
                 script: str = "prose", responses: list[dict] | None = None,
                 fail_with: str | None = None, workspace=None,
                 tokens_per_call: int | None = None):
        super().__init__(model_id=model_id, workspace=workspace)
        self.script = script
        self.scripts = list(responses or [])
        self.fail_with = fail_with
        self.tokens_per_call = tokens_per_call

    def _generate(self, request: dict) -> dict:
        if self.fail_with:
            raise ProviderError(f"fake provider is unavailable: {self.fail_with}")
        if self.scripts:
            scripted = self.scripts.pop(0)
            if scripted.get("__raise__"):
                raise ProviderError(str(scripted["__raise__"]))
            return dict(scripted)
        if self.script == "refuse":
            return {"text": "", "cited_fact_ids": [], "model_id": self.model_id,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                    "refusal_reason": "insufficient_evidence"}
        if self.script == "empty":
            return {"text": "", "cited_fact_ids": [], "model_id": self.model_id,
                    "usage": {"prompt_tokens": 1, "completion_tokens": 0},
                    "refusal_reason": None}
        if self.script == "garbage":
            # Malformed on purpose: no citations, an invented identifier and no
            # refusal. The gate has to catch all three, together.
            return {"text": "The WebMapServiceProExt automatically reconciles the "
                            "CatalogueRegistry.",
                    "cited_fact_ids": [], "model_id": self.model_id,
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "refusal_reason": None}
        if self.script == "uncited":
            return {"text": self._compose(request), "cited_fact_ids": [],
                    "model_id": self.model_id,
                    "usage": self._usage(request), "refusal_reason": None}
        if self.script == "invented":
            text = self._compose(request) + " It also exposes the SyncScheduler."
            return {"text": text, "cited_fact_ids": [self._ids(request)],
                    "model_id": self.model_id, "usage": self._usage(request),
                    "refusal_reason": None}
        return {"text": self._compose(request),
                "cited_fact_ids": self._ids(request), "model_id": self.model_id,
                "usage": self._usage(request), "refusal_reason": None}

    @staticmethod
    def _ids(request) -> list[str]:
        return [fact["id"] for fact in request["facts"]]

    def _usage(self, request) -> dict:
        if self.tokens_per_call is not None:
            return {"prompt_tokens": estimate_tokens(json.dumps(request)),
                    "completion_tokens": self.tokens_per_call}
        return {"prompt_tokens": estimate_tokens(json.dumps(request)),
                "completion_tokens": estimate_tokens(self._compose(request))}

    @staticmethod
    def _compose(request) -> str:
        """Deterministic prose over the request's facts, one sentence per fact."""
        if request["locale"] == "de":
            lead = f"Folgende Fakten sind belegt ({request['audience']}):"
        else:
            lead = f"The following is evidenced ({request['audience']}):"
        sentences = [lead]
        for fact in request["facts"]:
            detail = ""
            if fact.get("help"):
                detail = f" - {fact['help']}"
            elif fact.get("default") is not None:
                detail = f" (default {fact['default']})"
            sentences.append(f"{fact['name']} is a {fact['kind']} of the "
                             f"{fact['surface']} surface{detail}.")
        return " ".join(sentences)


class CommandAdapter(ProviderAdapter):
    """One allowlisted local binary, speaking JSON on stdin and stdout.

    The argv is fixed by the caller and validated before the process starts: no
    shell, no metacharacters, a scrubbed environment and a hard timeout, all of
    which the workspace enforces. This adapter is what makes "bring your own
    model" an operations decision instead of a code change, and it is what a suite
    uses to prove the pipeline survives a child that hangs, exits 1, prints
    secrets, or returns prose shaped like an instruction.
    """

    name = "command"
    reports_usage = True
    supports_refusal = True

    def __init__(self, *, argv: list[str], model_id: str, workspace,
                 timeout_s: float | None = None, env: dict | None = None):
        super().__init__(model_id=model_id, workspace=workspace)
        if not argv or any(not isinstance(token, str) or not token
                           for token in argv):
            raise AdapterPolicyError("command adapter needs a non-empty argv of "
                                     "strings")
        for token in argv:
            if re.search(r"[;&|`$<>\n\r]", token):
                raise AdapterPolicyError(
                    f"command adapter refuses a shell metacharacter in {token!r}")
        if workspace is None:
            raise AdapterPolicyError("command adapter needs a workspace boundary")
        self.argv = list(argv)
        self.timeout_s = timeout_s or workspace.budget("tool_wall_clock_s")
        self.env = env

    def healthcheck(self) -> tuple[bool, str]:
        try:
            Path(self.argv[0]).expanduser().stat()
        except OSError as exc:
            return False, f"{self.argv[0]}: {exc.strerror or exc}"
        return True, f"{self.argv[0]} is present"

    def _generate(self, request: dict) -> dict:
        env, withheld = workspace_lib.scrub_env(self.env)
        # The adapter's own credential, when the operator configured one, is the
        # only secret-shaped variable that reaches the child - and it reaches the
        # child named in the configuration, never a broad environment.
        payload = json.dumps(request, sort_keys=True)
        try:
            proc = subprocess.run(  # nosec B603 - validated argv, no shell
                self.argv, input=payload, capture_output=True, text=True,
                env=env, timeout=self.timeout_s,
                cwd=str(self.workspace.root), stdin=subprocess.PIPE)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"command provider timed out after {self.timeout_s}s") from exc
        except OSError as exc:
            raise ProviderError(f"command provider could not start: {exc}") from exc
        self.last_stderr = workspace_lib.scrub_text(proc.stderr or "")
        self.last_withheld = withheld
        if proc.returncode != 0:
            raise ProviderError(
                f"command provider exited {proc.returncode}: "
                f"{self.last_stderr[:300]}")
        try:
            response = json.loads(proc.stdout)
        except ValueError as exc:
            raise ProviderError(
                f"command provider did not answer JSON: {exc}") from exc
        if not isinstance(response, dict):
            raise ProviderError("command provider answered a "
                                f"{type(response).__name__}, not an object")
        return response


class HttpAdapter(ProviderAdapter):
    """POST the request to one endpoint; that endpoint is the whole network policy.

    ``allow_host`` is mandatory and exact: the adapter refuses any other host,
    including one the endpoint redirects to (redirects are refused rather than
    followed, because a redirect is how "one endpoint" becomes "any endpoint"). The
    bearer token comes from the environment by name, so it never appears in a
    configuration artifact, a report or a command line.
    """

    name = "http"
    reports_usage = True
    supports_refusal = True
    requires_credentials = True
    is_networked = True

    def __init__(self, *, url: str, model_id: str, token_env: str,
                 timeout_s: float | None = None, opener=None):
        super().__init__(model_id=model_id)
        self.url = url
        self.token_env = token_env
        self.timeout_s = timeout_s or 30.0
        self.opener = opener or urllib.request.urlopen
        try:
            parts = urllib.request.urlparse(url)
        except ValueError as exc:
            raise AdapterPolicyError(f"unparsable provider URL: {exc}") from exc
        if parts.scheme != "https":
            raise AdapterPolicyError(
                f"provider URL must be https, got {parts.scheme!r}: a model "
                "endpoint receives repository content and must not be reachable "
                "in the clear")
        if not parts.hostname:
            raise AdapterPolicyError("provider URL must name a host")
        self.host = parts.hostname

    def healthcheck(self) -> tuple[bool, str]:
        if not os.environ.get(self.token_env):
            return False, (f"{self.token_env} is not set: no credentials, no "
                           "model calls (fail-closed)")
        return True, f"configured for {self.host}"

    def _generate(self, request: dict) -> dict:
        token = os.environ.get(self.token_env)
        if not token:
            raise ProviderError(f"{self.token_env} is not set; refusing to call "
                                f"{self.host} unauthenticated")
        body = json.dumps(request, sort_keys=True).encode("utf-8")
        req = urllib.request.Request(  # nosec B310 - https, host pinned below
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "Authorization": f"Bearer {token}"})
        try:
            with self.opener(req, timeout=self.timeout_s) as response:
                if response.status >= 400:
                    raise ProviderError(
                        f"{self.host} answered {response.status}")
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"{self.host} answered {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"{self.host} is unreachable: {exc}") from exc
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError(f"{self.host} did not answer JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ProviderError(f"{self.host} answered a "
                                f"{type(parsed).__name__}, not an object")
        # The token never leaves this method: it is not in the request body, and
        # the response is returned as parsed data rather than as raw text a log
        # line might later carry.
        return parsed


ADAPTERS = {"fake": FakeAdapter, "command": CommandAdapter, "http": HttpAdapter}


def build_adapter(name: str, *, workspace, args=None) -> ProviderAdapter:
    """Build the configured adapter. Unknown names are a hard stop, never a fallback.

    Falling back to the fake adapter because a name was mistyped would publish
    deterministic placeholder prose under the project's name, which is the failure
    the epic exists to prevent.
    """
    try:
        factory = ADAPTERS[name]
    except KeyError:
        raise AdapterPolicyError(
            f"unknown provider {name!r}; the pipeline knows "
            f"{', '.join(sorted(ADAPTERS))}") from None
    args = args or {}
    if factory is FakeAdapter:
        return FakeAdapter(model_id=args.get("model_id", "mrmap-docs-model/fake-1"),
                           script=args.get("script", "prose"),
                           responses=args.get("responses"),
                           fail_with=args.get("fail_with"),
                           tokens_per_call=args.get("tokens_per_call"),
                           workspace=workspace)
    if factory is CommandAdapter:
        argv = args.get("argv")
        if not argv:
            raise AdapterPolicyError(
                "the command provider needs --provider-argv")
        return CommandAdapter(argv=argv, model_id=args["model_id"],
                              workspace=workspace,
                              timeout_s=args.get("timeout"),
                              env=args.get("env"))
    return HttpAdapter(url=args["url"], model_id=args["model_id"],
                       token_env=args.get("token_env", "MRMAP_DOCS_MODEL_TOKEN"),
                       timeout_s=args.get("timeout"))


def adapter_contract_checks(adapter_factory) -> list[tuple[str, bool, str]]:
    """The V-15 suite, run against any adapter.

    One function, one list of ``(name, ok, detail)``; every adapter passes the same
    list or it is not usable. ``adapter_factory`` is a zero-argument callable
    returning a fresh adapter per check, because an adapter keeps call state and a
    contract suite must not inherit it.

    The checks are exactly the four rules plus the two claims an adapter has to
    make about itself, with the reasoning for each stated where it earns its place.
    """
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), workspace_lib.scrub_text(detail)))

    request = build_request(
        claim_id="resources:resource:WebMapService", kind="narrative",
        audience="integrator", locale="en",
        facts=[contract.fact_ref(surface="resources", kind="resource",
                                 name="WebMapService", fields=["name"],
                                 evidence_id="sha256:" + "a" * 64)],
        evidence_refs=["sha256:" + "a" * 64])

    info = adapter_factory().describe()
    problems = contract.errors(contract.validate("provider", info))
    add("describe() answers a valid mrmap.docs.provider.v1", not problems,
        contract.issues_text(problems))
    add("the adapter reports usage", info["reports_usage"],
        "an adapter that cannot report model_id and usage cannot be used")
    add("the adapter can refuse", info["supports_refusal"],
        "without a refusal an unsupported topic becomes a guess")
    add("model_id carries the provider-independent prefix",
        bool(contract.MODEL_REF_RE.fullmatch(info["model_id"])), info["model_id"])

    try:
        response = adapter_factory().generate(request)
    except ProviderError as exc:
        add("answers a well-formed request", False, str(exc))
        return results
    issues = validate_response(response, request)
    add("answers with text that cites only facts it was given", not issues,
        contract.issues_text(issues))
    add("model_id in the response equals the adapter's",
        response["model_id"] == info["model_id"],
        f"{response['model_id']} != {info['model_id']}")
    usage = response["usage"]
    add("usage is reported as non-negative integers",
        isinstance(usage["prompt_tokens"], int)
        and isinstance(usage["completion_tokens"], int)
        and usage["prompt_tokens"] >= 0 and usage["completion_tokens"] >= 0,
        str(usage))
    add("a second identical call is reproducible or at least valid",
        not validate_response(adapter_factory().generate(request), request))

    # Refusal behaviour: a response that declines must be accepted as a valid
    # response by the contract, and must carry no text.
    refusal = {"schema": contract.RESPONSE_SCHEMA, "text": "", "cited_fact_ids": [],
               "model_id": info["model_id"],
               "usage": {"prompt_tokens": 0, "completion_tokens": 0},
               "refusal_reason": "insufficient_evidence"}
    add("a refusal is a valid response",
        not validate_response(refusal, request))
    add("a refusal carrying text is refused",
        bool(validate_response({**refusal, "text": "but here is a paragraph"},
                               request)))
    # And the gate's own teeth, asserted through the contract rather than trusted:
    # an unknown citation and an invented identifier must both be caught.
    add("a citation of a fact the request never carried is refused",
        bool(validate_response(
            {**response, "cited_fact_ids": ["resources:resource:NotReal"]},
            request)))
    add("prose naming an identifier no fact carries is refused",
        bool(validate_response(
            {**response, "text": "The FrobnicatorRegistry reconciles everything.",
             "cited_fact_ids": ["resources:resource:WebMapService"]}, request)))
    add("text without any citation is refused",
        bool(validate_response(
            {**response, "text": "Something about a service.",
             "cited_fact_ids": []}, request)))
    return results


def run_contract_suite(provider: str, *, workspace, args=None) -> tuple[int, list]:
    """Run :func:`adapter_contract_checks` against a configured adapter (V-15 in CI)."""
    factory = lambda: build_adapter(provider, workspace=workspace, args=args)  # noqa: E731
    results = adapter_contract_checks(factory)
    failed = [name for name, ok, _ in results if not ok]
    return (contract.EXIT_FAIL if failed else contract.EXIT_OK), results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="docs_providers.py")
    parser.add_argument("--provider", default="fake", choices=sorted(ADAPTERS))
    parser.add_argument("--model-id", default="mrmap-docs-model/fake-1")
    parser.add_argument("--script", default="prose")
    parser.add_argument("--argv", nargs="*", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--token-env", default="MRMAP_DOCS_MODEL_TOKEN")
    parser.add_argument("--root", default=".")
    parser.add_argument("--contract", action="store_true",
                        help="run the adapter contract suite (V-15) and exit")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work")
    config = {"model_id": args.model_id, "script": args.script, "argv": args.argv,
              "url": args.url, "token_env": args.token_env}
    try:
        if args.contract:
            status, results = run_contract_suite(args.provider, workspace=workspace,
                                                 args=config)
            for name, ok, detail in results:
                print(f"{'PASS' if ok else 'FAIL'}  {name}"
                      + (f"  [{detail[:200]}]" if detail and not ok else ""))
            passed = sum(1 for _, ok, _ in results if ok)
            print(f"{passed}/{len(results)} contract checks passed for "
                  f"{args.provider}")
            return status
        adapter = build_adapter(args.provider, workspace=workspace, args=config)
        request = build_request(
            claim_id="resources:resource:WebMapService", kind="narrative",
            audience="integrator", locale="en",
            facts=[contract.fact_ref(surface="resources", kind="resource",
                                     name="WebMapService",
                                     evidence_id="sha256:" + "a" * 64)])
        response = adapter.generate(request)
        print(json.dumps(response, indent=2, sort_keys=True))
        return contract.EXIT_OK
    except (ProviderError, AdapterPolicyError, contract.ContractError) as exc:
        print(f"provider refused: {workspace_lib.scrub_text(str(exc))}",
              file=sys.stderr)
        return contract.EXIT_CANNOT


# ``main`` uses argparse and the module imports abc/json/re/urllib only; keep the
# import list honest rather than importing argparse at the top through a wildcard.
import argparse  # noqa: E402  (used by main only, declared here to keep one place)

if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import re
from dataclasses import dataclass

# A shell command line inside a fenced bash/sh/shell/zsh block, or inside a
# file that is itself a shell script. A line that is blank or a comment is
# not a command. The bare word "Bash" is not an invocation: allowed-tools
# names that tool separately, as breadth.
_FENCE = re.compile(
    r"^[ \t]*```[ \t]*(bash|sh|shell|zsh)\b[^\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_SHEBANG = re.compile(r"^#!.*\b(?:bash|sh|zsh)\b")

# A network call is a URL, a shell client, or a call-shaped name. The word
# "fetch" in prose is not one: it has to look like a call.
_NETWORK = re.compile(
    r"""(?ix)
    \b(?:https?|wss?)://[^\s`<>)\]\'\"]+
    | (?<![\w.-])(?:curl|wget|httpie)(?![\w.-])
    | (?<![\w.-])fetch\s*\(
    | (?<![\w.-])axios\s*[.(]
    | (?<![\w.-])requests\.(?:get|post|put|patch|delete|head|request)\b
    | (?<![\w.-])urllib\.request\b
    | (?<![\w.-])http\.(?:Get|Post|Head|Do)\b
    | (?<![\w.-])net\.Dial\b
    | (?<![\w.-])WebFetch(?![\w.-])
    """
)

# Credential paths, not the word "credentials". A prose mention is not a path.
_CREDENTIAL = re.compile(
    r"""(?ix)
    ~/(\.ssh|\.aws|\.netrc|\.npmrc|\.pypirc|\.git-credentials)(?:/[^\s`'")\]]*)?
    | (?:^|[^\w./-])\.env(?:\.[A-Za-z0-9_-]+)?(?=$|[^\w.-])
    | /etc/(?:passwd|shadow)\b
    | (?:^|[^\w./-])(?:id_rsa|id_ed25519|id_ecdsa)(?:\.pub)?(?=$|[^\w.-])
    | (?:^|[^\w.-])(?:credentials|secrets)\.(?:json|ya?ml|txt|env)\b
    | (?:^|[^\w./-])\.git-credentials(?=$|[^\w.-])
    """
)


@dataclass(frozen=True)
class Risk:
    """What a static parse found. Counts, not a score.

    ``allowed_tools`` is None when the skill does not declare the field.
    An empty tuple means it declared the field and named nothing. Breadth
    is the length. There is no cutoff for "too broad".
    """

    bash: int = 0
    network: int = 0
    credentials: int = 0
    allowed_tools: tuple[str, ...] | None = None

    def to_dict(self) -> dict:
        return {
            "bash": self.bash,
            "network": self.network,
            "credentials": self.credentials,
            "allowedTools": (
                None if self.allowed_tools is None else list(self.allowed_tools)
            ),
        }


def tool_names(value) -> list[str]:
    """Split an allowed-tools value into tool names, dropping any arguments."""
    if value is None:
        return []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                names.extend(tool_names(item))
        return names
    if not isinstance(value, str):
        return []
    names = []
    buf: list[str] = []
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")" and depth:
            depth -= 1
            buf.append(ch)
        elif depth == 0 and ch in " \t\n,":
            _flush(buf, names)
        else:
            buf.append(ch)
    _flush(buf, names)
    return names


def _flush(buf: list[str], names: list[str]) -> None:
    token = "".join(buf).strip()
    buf.clear()
    if not token:
        return
    name = token.split("(", 1)[0].strip()
    if name:
        names.append(name)


def declared_tools(fields: dict[str, str], strict: dict | None) -> tuple[str, ...] | None:
    """The allowed-tools list, or None when the skill does not declare one.

    A parsed YAML value wins over the tolerant string, because a list is
    structure the line parser flattens.
    """
    if isinstance(strict, dict) and "allowed-tools" in strict:
        return tuple(tool_names(strict.get("allowed-tools")))
    if "allowed-tools" in fields:
        return tuple(tool_names(fields.get("allowed-tools")))
    return None


def _command_lines(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def shell_script(name: str, text: str) -> bool:
    if name.endswith((".sh", ".bash")):
        return True
    first = text.lstrip("\ufeff").splitlines()[:1]
    return bool(first and _SHEBANG.match(first[0]))


def bash_invocations(name: str, text: str) -> int:
    if shell_script(name, text):
        return _command_lines(text)
    return sum(_command_lines(body) for _, body in _FENCE.findall(text))


def assess(
    body: str,
    files: list[tuple[str, str]],
    allowed_tools: tuple[str, ...] | None,
) -> Risk:
    """Parse a skill body and its bundled text files. Frontmatter is excluded.

    ``allowed_tools`` is parsed by the caller from frontmatter, so a tool
    name there is breadth and not also a Bash invocation.
    """
    pieces = [("SKILL.md", body), *files]
    bash = network = credentials = 0
    for name, text in pieces:
        bash += bash_invocations(name, text)
        network += sum(1 for _ in _NETWORK.finditer(text))
        credentials += sum(1 for _ in _CREDENTIAL.finditer(text))
    return Risk(bash, network, credentials, allowed_tools)

"""RFC 9309 compliant robots.txt parser and policy enforcement."""

import logging
import re
from typing import Dict, List, Optional, Tuple, TypedDict

logger = logging.getLogger(__name__)


class RuleGroup(TypedDict):
    allow: List[Tuple[str, int]]
    disallow: List[Tuple[str, int]]
    crawl_delay: Optional[float]
    request_rate: Optional[str]


def _match_pattern(path: str, pattern: str) -> bool:
    """Evaluate RFC 9309 path pattern with wildcard (*) and end-anchor ($)."""
    if not pattern:
        return False

    escaped: List[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            escaped.append(".*")
        elif char == "$" and i == n - 1:
            escaped.append("$")
        else:
            escaped.append(re.escape(char))
        i += 1

    regex_str = "^" + "".join(escaped)
    try:
        return bool(re.search(regex_str, path))
    except re.error:
        return False


class RobotsTxtParser:
    """Parse robots.txt content according to RFC 9309 rules with extension support.

    Evaluation precedence:
    - Most specific (longest pattern length) matching directive wins.
    - If equally specific Allow and Disallow match, Allow wins.
    - Crawl-delay and Request-rate are supported extensions.
    """

    def __init__(self, content: str = "") -> None:
        # Map user-agent (lowercase) -> dict of rules
        self.groups: Dict[str, RuleGroup] = {}
        self.parse(content)

    def parse(self, content: str) -> None:
        """Parse raw robots.txt content into directive groups."""
        current_agents: List[str] = []
        in_rules = False

        for raw_line in content.splitlines():
            # Strip comments and trim whitespace
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue

            key, value = line.split(":", 1)
            directive = key.strip().lower()
            val = value.strip()

            if directive == "user-agent":
                if in_rules:
                    current_agents = []
                    in_rules = False
                agent = val.lower()
                current_agents.append(agent)
                if agent not in self.groups:
                    self.groups[agent] = {
                        "allow": [],
                        "disallow": [],
                        "crawl_delay": None,
                        "request_rate": None,
                    }
            elif directive in ("allow", "disallow"):
                in_rules = True
                if not current_agents:
                    continue
                for agent in current_agents:
                    rules = self.groups[agent]
                    if val:
                        # Store pattern and its octet length for RFC 9309 comparison
                        target_list = (
                            rules["allow"]
                            if directive == "allow"
                            else rules["disallow"]
                        )
                        target_list.append((val, len(val)))
            elif directive == "crawl-delay":
                in_rules = True
                # Extension directive
                try:
                    delay = float(val)
                    for agent in current_agents:
                        self.groups[agent]["crawl_delay"] = delay
                except ValueError:
                    pass
            elif directive == "request-rate":
                in_rules = True
                # Extension directive
                for agent in current_agents:
                    self.groups[agent]["request_rate"] = val
            elif not val and directive == "disallow":
                in_rules = True
                # Empty disallow means allow all / reset
                pass

    def _get_group_for_agent(self, user_agent: str) -> Optional[RuleGroup]:
        """Find the matching rule group according to RFC 9309 agent selection."""
        agent = user_agent.strip().lower()
        if agent in self.groups:
            return self.groups[agent]

        # Check token match (e.g., 'PrivateSearchCrawler' from full string)
        for registered_agent in self.groups:
            if registered_agent != "*" and (
                registered_agent in agent or agent in registered_agent
            ):
                return self.groups[registered_agent]

        # Fallback to wildcard
        if "*" in self.groups:
            return self.groups["*"]

        return None

    def can_fetch(self, user_agent: str, path: str) -> bool:
        """Check if path is allowed under RFC 9309 longest-match semantics."""
        group = self._get_group_for_agent(user_agent)
        if group is None:
            return True

        allow_rules = group["allow"]
        disallow_rules = group["disallow"]

        longest_allow_len = -1
        for pattern, length in allow_rules:
            if _match_pattern(path, pattern) and length > longest_allow_len:
                longest_allow_len = length

        longest_disallow_len = -1
        for pattern, length in disallow_rules:
            if _match_pattern(path, pattern) and length > longest_disallow_len:
                longest_disallow_len = length

        # If no rules match, default is allowed
        if longest_allow_len == -1 and longest_disallow_len == -1:
            return True

        # RFC 9309 2.2.2: If equally specific rules conflict, Allow wins
        if longest_allow_len >= longest_disallow_len:
            return True

        return False

    def get_crawl_delay(self, user_agent: str) -> float:
        """Get crawl delay extension in seconds, defaulting to 1.0s."""
        group = self._get_group_for_agent(user_agent)
        if group is not None and group.get("crawl_delay") is not None:
            delay = group["crawl_delay"]
            if isinstance(delay, (int, float)):
                return float(delay)

        # Check wildcard group
        if "*" in self.groups and self.groups["*"].get("crawl_delay") is not None:
            delay = self.groups["*"]["crawl_delay"]
            if isinstance(delay, (int, float)):
                return float(delay)

        return 1.0

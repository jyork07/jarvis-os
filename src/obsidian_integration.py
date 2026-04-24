"""
Obsidian Integration Module
Provides bidirectional memory integration between JARVIS, OpenClaw, and Obsidian
"""

import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


class ObsidianBrain:
    """Main interface for Obsidian Brain operations"""

    STOP_WORDS = {
        "the", "and", "for", "with", "from", "that", "this", "into", "your", "have", "will",
        "jarvis", "openclaw", "note", "notes", "file", "files", "index", "brain", "main",
    }

    def __init__(self, obsidian_path=None, api_key=None, api_url=None):
        if obsidian_path is None:
            obsidian_path = os.environ.get("JARVIS_OBSIDIAN_PATH", "C:\\Users\\jamie\\Documents\\JARVIS-Brain")
        self.obsidian_path = Path(obsidian_path)
        self.api_key = (api_key if api_key is not None else os.environ.get("JARVIS_OBSIDIAN_API_KEY", "")).strip()
        self.api_url = (api_url if api_url is not None else os.environ.get("JARVIS_OBSIDIAN_API_URL", "http://127.0.0.1:27123")).strip()
        self.vault_name = self.obsidian_path.name
        self.active_memory_path = self.obsidian_path / "04 - ACTIVE MEMORY"
        self.knowledge_base_path = self.obsidian_path / "03 - KNOWLEDGE BASE"
        self.agent_management_path = self.obsidian_path / "02 - AGENT MANAGEMENT"
        self.config_path = self.obsidian_path / "01 - SYSTEM CONFIGURATION"
        self.generated_path = self.obsidian_path / "00 - JARVIS"
        self.vault_index_path = self.generated_path / "JARVIS Vault Index.md"
        self.main_brain_path = self.generated_path / "JARVIS Main Brain.md"
        self.last_link_summary = {}

        for path in [
            self.active_memory_path,
            self.knowledge_base_path,
            self.agent_management_path,
            self.config_path,
            self.generated_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _safe_title(self, title):
        cleaned = re.sub(r"[^\w\s-]", "", str(title)).strip()
        return cleaned or "Untitled"

    def _all_markdown_files(self):
        files = []
        for file_path in self.obsidian_path.rglob("*.md"):
            files.append(file_path)
        return sorted(files, key=lambda p: str(p).lower())

    def _content_files(self):
        return [
            file_path for file_path in self._all_markdown_files()
            if file_path not in {self.vault_index_path, self.main_brain_path}
        ]

    def _relative(self, file_path):
        return Path(file_path).resolve().relative_to(self.obsidian_path.resolve())

    def _tokenize(self, value):
        tokens = set()
        for token in re.findall(r"[A-Za-z0-9]{3,}", str(value or "").lower()):
            if token not in self.STOP_WORDS:
                tokens.add(token)
        return tokens

    def _append_related_link(self, file_path, target_path, reference_type="related"):
        path = Path(file_path)
        target = Path(target_path)
        if not path.exists() or not target.exists() or path == target:
            return False

        relative_target = self._relative(target).as_posix()
        reference_link = f"- [{target.stem}](<{relative_target}>) ({reference_type})"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if reference_link in content:
            return False

        block = "\n\n## Related\n" if "\n## Related\n" not in content else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{block}{reference_link}\n")
        return True

    def _api_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_api_status(self):
        status = {
            "configured": bool(self.api_key),
            "api_url": self.api_url or None,
            "reachable": False,
            "status_code": None,
            "error": None,
        }
        if not self.api_key or not self.api_url or requests is None:
            if requests is None:
                status["error"] = "requests_not_available"
            return status

        try:
            response = requests.get(self.api_url.rstrip("/"), headers=self._api_headers(), timeout=3)
            status["reachable"] = True
            status["status_code"] = response.status_code
        except Exception as exc:
            status["error"] = str(exc)
        return status

    def create_memory_entry(self, title, content, tags=None, source="JARVIS", category="general"):
        """Create a new memory entry in Obsidian"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_title = self._safe_title(title)
        filename = f"{safe_title} {datetime.now().strftime('%Y%m%d-%H%M%S')}.md"

        md_content = f"""# {title}

> **Source**: {source}
> **Created**: {timestamp}
> **Category**: {category}
> **Tags**: {', '.join(tags) if tags else 'none'}

---

## Content

{content}

---

## Metadata

- **Source System**: {source}
- **Entry Type**: Memory
- **Vault Index**: [JARVIS Vault Index](<00 - JARVIS/JARVIS Vault Index.md>)
- **Main Brain**: [JARVIS Main Brain](<00 - JARVIS/JARVIS Main Brain.md>)
"""

        if category == "knowledge":
            file_path = self.knowledge_base_path / filename
        elif category == "agent":
            file_path = self.agent_management_path / filename
        else:
            file_path = self.active_memory_path / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return str(file_path)

    def search_memory(self, query, limit=10):
        """Search memory entries by content"""
        results = []
        query_lower = str(query or "").lower()
        for file_path in self._all_markdown_files():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue
            if query_lower in content.lower():
                source = self._relative(file_path).parts[0] if self._relative(file_path).parts else "vault"
                results.append({
                    "path": str(file_path),
                    "title": file_path.stem,
                    "content": content[:500] + "..." if len(content) > 500 else content,
                    "source": source,
                })
        return results[:limit]

    def get_memory(self, filename):
        """Retrieve a specific memory entry"""
        file_path = self.obsidian_path / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def update_memory(self, filename, new_content):
        """Update an existing memory entry"""
        file_path = self.obsidian_path / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_content = original_content + f"\n\n---\n**Updated**: {timestamp}\n\n{new_content}"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            return True
        return False

    def create_agent_memory(self, agent_name, message, context=""):
        """Create memory entry for agent interaction"""
        title = f"{agent_name} Interaction"
        content = f"## Agent: {agent_name}\n\n### Message\n{message}\n\n### Context\n{context}\n\n### Timestamp\n{datetime.now().isoformat()}"
        return self.create_memory_entry(title, content, tags=[agent_name], source="OpenClaw", category="agent")

    def create_jarvis_memory(self, user_message, jarvis_response, session_id=""):
        """Create memory entry for JARVIS interaction"""
        title = f"JARVIS Session {session_id}"
        content = f"## User Message\n{user_message}\n\n## JARVIS Response\n{jarvis_response}\n\n### Session ID\n{session_id}\n\n### Timestamp\n{datetime.now().isoformat()}"
        return self.create_memory_entry(title, content, tags=["JARVIS", "chat"], source="JARVIS", category="general")

    def get_recent_memories(self, limit=10):
        """Get recent memory entries"""
        all_files = []
        for file_path in self._content_files():
            try:
                all_files.append((file_path, file_path.stat().st_mtime))
            except OSError:
                continue

        all_files.sort(key=lambda x: x[1], reverse=True)
        results = []
        for file_path, mtime in all_files[:limit]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            results.append({
                "path": str(file_path),
                "title": file_path.stem,
                "content": content[:300] + "..." if len(content) > 300 else content,
                "modified": datetime.fromtimestamp(mtime).isoformat(),
            })
        return results

    def create_cross_reference(self, source_file, target_file, reference_type="related"):
        """Create a cross-reference link between two memory entries"""
        source_path = Path(source_file)
        target_path = Path(target_file)
        created_forward = self._append_related_link(source_path, target_path, reference_type)
        created_back = self._append_related_link(target_path, source_path, reference_type)
        return created_forward or created_back

    def build_vault_index(self):
        files = self._content_files()
        grouped = defaultdict(list)
        for file_path in files:
            rel = self._relative(file_path)
            folder = rel.parent.as_posix() if str(rel.parent) != "." else "/"
            grouped[folder].append(rel)

        lines = [
            "# JARVIS Vault Index",
            "",
            f"> Generated: {datetime.now().isoformat()}",
            f"> Vault: {self.vault_name}",
            f"> Markdown files indexed: {len(files)}",
            f"> Main Brain: [JARVIS Main Brain](<00 - JARVIS/JARVIS Main Brain.md>)",
            "",
            "---",
            "",
        ]

        for folder in sorted(grouped):
            lines.append(f"## {folder}")
            lines.append("")
            for rel in grouped[folder]:
                lines.append(f"- [{rel.stem}](<{rel.as_posix()}>)")
            lines.append("")

        with open(self.vault_index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")

        return {
            "path": str(self.vault_index_path),
            "file_count": len(files),
            "folders": len(grouped),
        }

    def build_main_brain(self):
        files = self._content_files()
        grouped = defaultdict(list)
        for file_path in files:
            rel = self._relative(file_path)
            folder = rel.parent.as_posix() if str(rel.parent) != "." else "/"
            grouped[folder].append(rel)

        sections = [
            "# JARVIS Main Brain",
            "",
            f"> Generated: {datetime.now().isoformat()}",
            f"> Vault: {self.vault_name}",
            "> Purpose: central hub for memory, knowledge, reference, history, and system notes.",
            "",
            "## Core Hubs",
            "",
            f"- [JARVIS Vault Index](<{self._relative(self.vault_index_path).as_posix()}>)",
            "- [ACTIVE MEMORY](<04 - ACTIVE MEMORY>)",
            "- [KNOWLEDGE BASE](<03 - KNOWLEDGE BASE>)",
            "- [AGENT MANAGEMENT](<02 - AGENT MANAGEMENT>)",
            "- [SYSTEM CONFIGURATION](<01 - SYSTEM CONFIGURATION>)",
            "",
            "## Brain Map",
            "",
        ]

        for folder in sorted(grouped):
            sections.append(f"### {folder}")
            sections.append("")
            for rel in grouped[folder]:
                sections.append(f"- [{rel.stem}](<{rel.as_posix()}>)")
            sections.append("")

        with open(self.main_brain_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sections).strip() + "\n")

        return {"path": str(self.main_brain_path)}

    def link_all_files(self):
        index_info = self.build_vault_index()
        main_brain_info = self.build_main_brain()
        files = self._content_files()
        created_links = 0

        grouped = defaultdict(list)
        token_map = {}
        for file_path in files:
            rel = self._relative(file_path)
            folder = rel.parent.as_posix() if str(rel.parent) != "." else "/"
            grouped[folder].append(file_path)
            token_map[file_path] = self._tokenize(file_path.stem)

        for file_path in files:
            if self._append_related_link(file_path, self.main_brain_path, "brain-hub"):
                created_links += 1
            if self._append_related_link(file_path, self.vault_index_path, "vault-index"):
                created_links += 1

        for folder_files in grouped.values():
            ordered = sorted(folder_files, key=lambda p: str(p).lower())
            for idx, file_path in enumerate(ordered):
                if idx > 0 and self._append_related_link(file_path, ordered[idx - 1], "sibling"):
                    created_links += 1
                if idx < len(ordered) - 1 and self._append_related_link(file_path, ordered[idx + 1], "sibling"):
                    created_links += 1

        for file_path in files:
            similarities = []
            source_tokens = token_map.get(file_path, set())
            if not source_tokens:
                continue
            for candidate in files:
                if candidate == file_path:
                    continue
                overlap = len(source_tokens & token_map.get(candidate, set()))
                if overlap > 0:
                    similarities.append((overlap, str(candidate).lower(), candidate))
            similarities.sort(reverse=True)
            for _, _, candidate in similarities[:3]:
                if self._append_related_link(file_path, candidate, "semantic"):
                    created_links += 1

        # Keyword linking (link filenames found in content)
        all_titles = {f.stem: f for f in files}
        sorted_titles = sorted(all_titles.keys(), key=len, reverse=True)
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                for title in sorted_titles:
                    if title.lower() in content and title.lower() != file_path.stem.lower():
                        if self._append_related_link(file_path, all_titles[title], "keyword"):
                            created_links += 1
            except: continue

        recent = self.get_recent_memories(limit=20)
        timeline_links = 0
        for idx in range(len(recent) - 1):
            if self.create_cross_reference(recent[idx]["path"], recent[idx + 1]["path"], "timeline"):
                created_links += 1
                timeline_links += 1

        summary = {
            **index_info,
            **main_brain_info,
            "crosslinks_created": created_links,
            "timeline_links": timeline_links,
            "linked_files": len(files),
        }
        self.last_link_summary = summary
        return summary

    def get_status(self):
        files = self._content_files()
        return {
            "enabled": True,
            "obsidian_path": str(self.obsidian_path),
            "active_memory_path": str(self.active_memory_path),
            "knowledge_base_path": str(self.knowledge_base_path),
            "agent_management_path": str(self.agent_management_path),
            "vault_index_path": str(self.vault_index_path),
            "main_brain_path": str(self.main_brain_path),
            "vault_name": self.vault_name,
            "markdown_file_count": len(files),
            "api": self.get_api_status(),
            "last_link_summary": self.last_link_summary,
        }


_obsidian_brain = None


def get_obsidian_brain():
    """Get or create the singleton Obsidian Brain instance"""
    global _obsidian_brain
    if _obsidian_brain is None:
        _obsidian_brain = ObsidianBrain()
    return _obsidian_brain

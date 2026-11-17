"""File and folder search module utilizing Spotlight mdfind and fast filesystem traversals."""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("MacAssistant.FileSearch")


class FileSearchService:
    """Provides high-performance search for files, PDFs, projects, and folders."""

    @staticmethod
    def _run_mdfind(query: str, only_in: Optional[str] = None, limit: int = 5) -> List[str]:
        """Executes macOS mdfind (Spotlight) safely with argument lists."""
        cmd = ["/usr/bin/mdfind"]
        if only_in:
            cmd.extend(["-onlyin", str(only_in)])
        cmd.append(query)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return lines[:limit]
        except Exception as e:
            logger.debug("mdfind execution error: %s", e)
            return []

    @classmethod
    def find_flutter_projects(cls, search_root: Optional[str] = None, limit: int = 5) -> List[Path]:
        """
        Locates Flutter projects by finding 'pubspec.yaml' files.
        Combines Spotlight with directory traversal fallback.
        """
        root = search_root or str(Path.home() / "Documents")
        logger.info("Searching for Flutter projects in: %s", root)

        # 1. Try Spotlight mdfind query
        results = cls._run_mdfind("kMDItemFSName == 'pubspec.yaml'", only_in=root, limit=limit * 2)
        project_dirs = []
        for r in results:
            p = Path(r)
            if p.name == "pubspec.yaml":
                project_dirs.append(p.parent)

        # 2. Fallback filesystem scan if Spotlight has no index
        if not project_dirs:
            try:
                base = Path(root).expanduser()
                if base.exists():
                    for yaml_file in base.glob("**/pubspec.yaml"):
                        if not any(ignored in str(yaml_file) for ignored in [".git", "venv", ".symlinks", "build"]):
                            project_dirs.append(yaml_file.parent)
                            if len(project_dirs) >= limit:
                                break
            except Exception as e:
                logger.debug("Filesystem glob error: %s", e)

        return project_dirs[:limit]

    @classmethod
    def find_pdfs(cls, keyword: Optional[str] = None, search_root: Optional[str] = None, limit: int = 5) -> List[Path]:
        """
        Locates PDF files matching optional keywords.
        """
        root = search_root or str(Path.home())
        logger.info("Searching for PDFs with keyword '%s' in: %s", keyword, root)

        # Spotlight query for PDF content type
        if keyword:
            query = f"kMDItemContentType == 'com.adobe.pdf' && kMDItemFSName == '*{keyword}*'c"
        else:
            query = "kMDItemContentType == 'com.adobe.pdf'"

        results = cls._run_mdfind(query, only_in=root, limit=limit)
        pdf_paths = [Path(r) for r in results]

        # Filesystem fallback
        if not pdf_paths:
            try:
                search_dir = Path(root).expanduser()
                if search_dir.exists():
                    clean_kw = keyword.lower().strip() if keyword else ""
                    for f in search_dir.glob("**/*.pdf"):
                        if not any(ignored in str(f) for ignored in [".git", "venv", "Trash", "Library"]):
                            if not clean_kw or clean_kw in f.name.lower():
                                pdf_paths.append(f)
                                if len(pdf_paths) >= limit:
                                    break
            except Exception as e:
                logger.debug("PDF glob error: %s", e)

        return pdf_paths[:limit]

    @classmethod
    def search_files(cls, name_query: str, search_root: Optional[str] = None, limit: int = 5) -> List[Path]:
        """General file/folder search by filename."""
        root = search_root or str(Path.home())
        query = f"kMDItemFSName == '*{name_query}*'c"
        results = cls._run_mdfind(query, only_in=root, limit=limit)
        return [Path(r) for r in results[:limit]]

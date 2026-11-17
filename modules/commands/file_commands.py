"""File and directory search command handlers."""

import subprocess
from pathlib import Path
from typing import Any, Dict, List


def handle_search_flutter_projects(args: Dict[str, Any]) -> Dict[str, Any]:
    """Finds active Flutter projects by locating pubspec.yaml."""
    results: List[Dict[str, str]] = []
    search_dirs = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Projects"
    ]

    try:
        # Fast spotlight search
        cmd = ["/usr/bin/mdfind", "kMDItemFSName == 'pubspec.yaml'"]
        out = subprocess.check_output(cmd, text=True, timeout=5)
        for line in out.strip().split("\n"):
            p = line.strip()
            if p:
                proj_dir = Path(p).parent
                results.append({"name": proj_dir.name, "path": str(proj_dir)})
    except Exception:
        # Filesystem fallback
        for base in search_dirs:
            if base.exists():
                try:
                    for pub in base.glob("**/pubspec.yaml"):
                        proj_dir = pub.parent
                        results.append({"name": proj_dir.name, "path": str(proj_dir)})
                        if len(results) >= 5:
                            break
                except Exception:
                    pass

    return {
        "success": True,
        "count": len(results),
        "projects": results[:5]
    }


def handle_search_files(args: Dict[str, Any]) -> Dict[str, Any]:
    """Searches for files matching name or extension (e.g. pdf)."""
    query = args.get("query", "").strip()
    file_type = args.get("file_type", "").lower()
    
    predicate = []
    if file_type:
        predicate.append(f"kMDItemFSName == '*.{file_type}'")
    if query:
        predicate.append(f"kMDItemTextContent == '*{query}*'c || kMDItemFSName == '*{query}*'c")

    if not predicate:
        return {"success": False, "error": "Query or file_type must be provided."}

    mdfind_query = " && ".join(predicate)
    found = []
    try:
        cmd = ["/usr/bin/mdfind", "-onlyin", str(Path.home()), mdfind_query]
        out = subprocess.check_output(cmd, text=True, timeout=5)
        for line in out.strip().split("\n"):
            p = line.strip()
            if p:
                found.append(p)
                if len(found) >= 5:
                    break
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {"success": True, "count": len(found), "files": found}


def handle_open_folder(args: Dict[str, Any]) -> Dict[str, Any]:
    """Opens a folder in Finder."""
    folder_path = args.get("folder_path", "").strip()
    from modules.services.mac_automation import MacAutomationService
    success, msg = MacAutomationService.open_folder(folder_path)
    return {"success": success, "message": msg}

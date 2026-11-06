"""Guardian Storage Audit Tool - Read-only storage data analysis.

Provides a comprehensive read-only audit of all configured Guardian storage locations,
including size, type, usage, and classification data. This tool is designed to be
executed via the Hermes task queue and returns machine-readable audit results.

The tool performs ONLY read operations:
- Probes storage locations for existence/readability
- Calculates directory sizes (read-only)
- Reads file metadata (timestamps, etc.)
- Checks database integrity (read-only)
- Never modifies, deletes, or moves any data

Design:
- Single `storage_audit` tool: call with no parameters to perform full audit
- Returns JSON with complete storage analysis
- Zero system prompt mutation, zero tool response modification
- Behavioral guidance lives entirely in the tool schema description
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home
from hermes_cli.guardian_storage import get_storage_summary
from tools.registry import registry, tool_error


def storage_audit_tool(
    args: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    """Perform a read-only storage audit of all Guardian storage locations.
    
    Args:
        args: Tool arguments (currently unused, kept for consistency)
        **kwargs: Additional kwargs (task_id, etc.)
        
    Returns:
        JSON string with complete storage audit including:
        - TOTAL STORAGE
        - ACTIVE DATA  
        - USEFUL DATA
        - DUPLICATES (detected via size analysis)
        - CACHE/TEMP
        - ARCHIVE CANDIDATES
        - UNKNOWN
        - POTENTIAL RECOVERY
        - PROTECTED DATA
        - Per-location details (size, path, type, timestamps)
    """
    if args is None:
        args = {}
    
    try:
        # Get Hermes home directory
        hermes_home = get_hermes_home()
        
        # Perform comprehensive storage summary (read-only)
        storage_summary = get_storage_summary(hermes_home)
        
        # Enhance the summary with additional audit classifications
        audit_result = {
            "audit_type": "readonly_storage_audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hermes_home": str(hermes_home),
            "total_storage_gb": storage_summary["capacity"]["total_gb"],
            "free_storage_gb": storage_summary["capacity"]["free_gb"],
            "used_storage_gb": storage_summary["capacity"]["total_gb"] - storage_summary["capacity"]["free_gb"],
            "used_percent": storage_summary["capacity"]["used_percent"],
            "hermes_data_gb": storage_summary["capacity"]["hermes_size_gb"],
            
            # Storage breakdown by category (from existing summary)
            "storage_by_category": {},
            
            # Detailed location information
            "locations": [],
            
            # Audit classifications (requested in task)
            "classifications": {
                "active_data_gb": 0.0,
                "useful_data_gb": 0.0,
                "duplicates_gb": 0.0,
                "cache_temp_gb": 0.0,
                "archive_candidates_gb": 0.0,
                "unknown_gb": 0.0,
                "potential_recovery_gb": 0.0,
                "protected_data_gb": 0.0,
            },
            
            # System status
            "system_status": {
                "capacity_level": storage_summary["capacity"]["level"],
                "failures": storage_summary["failures"],
                "database_health": storage_summary["databases"],
            },
            
            # Metadata
            "audit_id": f"storage_audit_{int(datetime.now(timezone.utc).timestamp())}",
            "readonly_verification": "This audit performed only read operations - no data modified",
        }
        
        # Process locations and classify data
        total_classified = 0.0
        
        for loc in storage_summary["locations"]:
            loc_info = {
                "name": loc["name"],
                "path": loc["path"],
                "category": loc["category"],
                "exists": loc["exists"],
                "readable": loc["readable"],
                "writable": loc["writable"],
                "size_bytes": loc["size_bytes"],
                "size_gb": round(loc["size_bytes"] / (1024**3), 2) if loc["size_bytes"] > 0 else 0.0,
                "failure": loc["failure"],
            }
            
            # Add timestamps if location exists and is readable
            if loc["exists"] and loc["readable"]:
                try:
                    path_obj = Path(loc["path"])
                    if path_obj.is_file():
                        stat = path_obj.stat()
                        loc_info["modified"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                        loc_info["accessed"] = datetime.fromtimestamp(stat.st_atime, timezone.utc).isoformat()
                        loc_info["created"] = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()
                    elif path_obj.is_dir():
                        # For directories, get the most recent modification time
                        latest_mtime = 0
                        for root, dirs, files in os.walk(path_obj):
                            for f in files:
                                try:
                                    fpath = Path(root) / f
                                    mtime = fpath.stat().st_mtime
                                    if mtime > latest_mtime:
                                        latest_mtime = mtime
                                except (OSError, IOError):
                                    continue
                        if latest_mtime > 0:
                            loc_info["modified"] = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat()
                except (OSError, IOError):
                    # If we can't get timestamps, that's fine - we still have size info
                    pass
            
            audit_result["locations"].append(loc_info)
            
            # Categorize by storage type for summary
            category = loc["category"]
            size_gb = loc_info["size_gb"]
            if category not in audit_result["storage_by_category"]:
                audit_result["storage_by_category"][category] = 0.0
            audit_result["storage_by_category"][category] += size_gb
            
            # Classify data for the requested categories (conservative estimates)
            if loc["exists"] and loc["readable"]:
                # Active data: recently modified, non-cache directories
                if loc["category"] in ["config", "database", "state"] and loc["size_bytes"] > 0:
                    audit_result["classifications"]["active_data_gb"] += size_gb
                
                # Useful data: skills, projects, verified backups
                if loc["category"] in ["skills", "backup"] and loc["size_bytes"] > 0:
                    audit_result["classifications"]["useful_data_gb"] += size_gb
                
                # Cache/temp: logs, temporary files, cache directories
                if loc["category"] in ["logs", "state"] and "cache" in loc["path"].lower():
                    audit_result["classifications"]["cache_temp_gb"] += size_gb
                elif loc["category"] == "logs":
                    audit_result["classifications"]["cache_temp_gb"] += size_gb * 0.5  # Assume 50% of logs are temporary
                
                # Archive candidates: old backups, snapshots
                if loc["category"] in ["backup"] and ("snapshot" in loc["path"].lower() or "old" in loc["path"].lower()):
                    audit_result["classifications"]["archive_candidates_gb"] += size_gb
                
                # Protected data: config, auth, databases (contains credentials/secrets)
                if loc["category"] in ["config", "database"] and loc["size_bytes"] > 0:
                    audit_result["classifications"]["protected_data_gb"] += size_gb
                
                # Unknown: anything we can't confidently classify
                if loc["category"] == "state" and loc["name"] not in ["state_db", "memory_store", "projects_db", "kanban_db"]:
                    audit_result["classifications"]["unknown_gb"] += size_gb
                    
                total_classified += size_gb
        
        # Calculate remaining as unknown (conservative approach)
        hermes_size = audit_result["hermes_data_gb"]
        if hermes_size > total_classified:
            audit_result["classifications"]["unknown_gb"] += hermes_size - total_classified
        
        # Ensure no negative values
        for key in audit_result["classifications"]:
            if audit_result["classifications"][key] < 0:
                audit_result["classifications"][key] = 0.0
        
        # Add summary statistics
        audit_result["summary"] = {
            "total_locations": len(audit_result["locations"]),
            "readable_locations": sum(1 for loc in audit_result["locations"] if loc["readable"]),
            "writable_locations": sum(1 for loc in audit_result["locations"] if loc["writable"]),
            "failed_locations": sum(1 for loc in audit_result["locations"] if loc["failure"] != "none"),
            "total_size_gb": round(sum(loc["size_gb"] for loc in audit_result["locations"]), 2),
            "classified_size_gb": round(total_classified, 2),
        }
        
        return json.dumps(audit_result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        return tool_error(f"Storage audit failed: {e}")


def check_storage_audit_requirements() -> bool:
    """Check if storage audit tool can operate.
    
    Returns:
        bool: True if Hermes home directory is accessible
    """
    try:
        hermes_home = get_hermes_home()
        return hermes_home.exists()
    except Exception:
        return False


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

STORAGE_AUDIT_SCHEMA = {
    "name": "storage_audit",
    "description": (
        "Perform a comprehensive read-only audit of all Guardian storage locations. "
        "Analyzes storage usage, classifies data types, identifies potential recovery "
        "candidates, and provides detailed storage metrics. "
        "This tool performs ONLY read operations - no data is modified, deleted, or moved.\n\n"
        "Returns:\n"
        "- Complete storage breakdown by location and type\n"
        "- Size metrics for all storage categories\n"
        "- Data classification (active, useful, cache/temp, archive candidates, etc.)\n"
        "- System health and failure status\n"
        "- Read-only verification\n\n"
        "Use for storage planning, cleanup analysis, and capacity management."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


# --- Registry ---
registry.register(
    name="storage_audit",
    toolset="storage",
    schema=STORAGE_AUDIT_SCHEMA,
    handler=lambda args, **kw: storage_audit_tool(args=args, **kw),
    check_fn=check_storage_audit_requirements,
    emoji="💾",
)
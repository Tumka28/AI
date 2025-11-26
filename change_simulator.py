# AI/FeatureImpact/change_simulator.py
import difflib
import os

class ChangeSimulator:
    """
    Creates a diff-like preview for proposed patch/edits.
    If the user supplies a 'patch' as mapping path->new_content, we show diff.
    """

    def preview_patch(self, original_files, patch_map):
        """
        original_files: list of {"path","content"}
        patch_map: dict path->new_content
        returns: list of {"path","diff"}
        """
        orig_map = {f["path"]: f["content"] for f in original_files}
        previews = []

        for path, new_content in patch_map.items():
            old = orig_map.get(path, "")
            diff = "\n".join(difflib.unified_diff(
                old.splitlines(), new_content.splitlines(),
                fromfile=path, tofile=path + ".patched", lineterm=""
            ))
            previews.append({"path": path, "diff": diff})
        return previews

    def simple_patch_from_description(self, files, description):
        """
        Uses an LLM to propose concrete small edits for a short description.
        For safety this only returns suggested patched content (not auto-applied).
        """
        from utils.llm_client import LLMClient
        llm = LLMClient()

        # pick a few relevant files as candidates (first 5)
        candidates = files[:5]
        snippets = "\n\n".join([f"FILE: {f['path']}\n{f['content'][:1200]}" for f in candidates])

        prompt = f"""
You are an assistant that proposes a small safe code edit based on the description.

Change description:
{description}

Candidate files (showing top-of-file snippets):
{snippets}

Return JSON mapping: {{ "path/to/file": "new file content", ... }}
Only return JSON.
"""
        try:
            res = llm.query("deepseek-coder-v2:16b", prompt)
            import json
            return json.loads(res)
        except Exception:
            return {}

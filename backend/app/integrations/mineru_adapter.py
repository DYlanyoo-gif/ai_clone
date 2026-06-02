from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration (read from Settings / env) ──
try:
    from app.core.config import get_settings as _get_settings
except ImportError:
    _get_settings = None

MINERU_OUTPUT_BASE = os.getenv("MINERU_OUTPUT_DIR", os.path.join("..", "data", "mineru_output"))


@dataclass
class ParsedDocument:
    text: str
    markdown_path: Optional[str] = None
    json_path: Optional[str] = None
    images_dir: Optional[str] = None
    parser: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class MineruStatus:
    installed: bool
    command: Optional[str]
    version_or_help: Optional[str]
    error: Optional[str]
    enabled: bool


def _run_detect_cmd(cmd_name: str, args: list[str], timeout: int = 15) -> tuple[bool, str]:
    """Run a detection command and return (success, output_or_error)."""
    try:
        result = subprocess.run(
            [cmd_name] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        combined = (result.stdout + result.stderr).strip()
        if result.returncode == 0 or combined:
            return True, combined[:500]
        return False, f"exit code {result.returncode}"
    except FileNotFoundError:
        return False, f"command '{cmd_name}' not found in PATH"
    except subprocess.TimeoutExpired:
        return False, f"command '{cmd_name}' timed out"
    except Exception as e:
        return False, str(e)


def detect_mineru() -> MineruStatus:
    """Detect whether MinerU is installed and which CLI command is available.

    Returns MineruStatus with installed/command/version_or_help/error/enabled.
    """
    enabled_env = os.getenv("MINERU_ENABLED", "true").lower()
    enabled = enabled_env in ("1", "true", "yes")

    for cmd_name in ("mineru", "magic-pdf"):
        ok, output = _run_detect_cmd(cmd_name, ["--version"], timeout=15)
        if ok:
            return MineruStatus(
                installed=True,
                command=cmd_name,
                version_or_help=output[:200],
                error=None,
                enabled=enabled,
            )
        # Try --help as fallback
        ok2, output2 = _run_detect_cmd(cmd_name, ["--help"], timeout=15)
        if ok2:
            return MineruStatus(
                installed=True,
                command=cmd_name,
                version_or_help=output2[:200],
                error=None,
                enabled=enabled,
            )

    # Neither command found – collect last error
    _, last_error = _run_detect_cmd("mineru", ["--version"], timeout=10)
    _, last_error2 = _run_detect_cmd("magic-pdf", ["--version"], timeout=10)

    return MineruStatus(
        installed=False,
        command=None,
        version_or_help=None,
        error=f"mineru: {last_error}; magic-pdf: {last_error2}",
        enabled=enabled,
    )


def _pick_command() -> Optional[str]:
    """Return the available MinerU CLI command name, or None."""
    status = detect_mineru()
    return status.command


def _build_command(cmd_name: str, input_path: str, output_dir: str) -> list[str]:
    """Build the CLI command dynamically from Settings / env.

    Default: mineru -p <input> -o <output> -b pipeline -m auto -l ch
    """
    from app.core.config import get_settings as _s

    settings = _s()

    cmd = [cmd_name, "-p", input_path, "-o", output_dir]

    # Backend & method — only for 'mineru' command (not magic-pdf)
    if cmd_name == "mineru":
        cmd.extend(["-b", settings.mineru_backend])
        cmd.extend(["-m", settings.mineru_method])
        cmd.extend(["-l", settings.mineru_lang])

    # Page range
    if settings.mineru_start_page is not None:
        cmd.extend(["-s", str(settings.mineru_start_page)])
    if settings.mineru_end_page is not None:
        cmd.extend(["-e", str(settings.mineru_end_page)])

    # Boolean flags — must pass explicit true/false value, not bare flag
    cmd.extend(["--formula", "true" if settings.mineru_formula else "false"])
    cmd.extend(["--table", "true" if settings.mineru_table else "false"])
    cmd.extend(["--image-analysis", "true" if settings.mineru_image_analysis else "false"])

    return cmd


def _find_output_files(output_dir: Path) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Scan output_dir for .md, .json, and images/ directory.

    Returns (md_path, json_path, images_dir).
    """
    md_path = None
    json_path = None
    images_dir = None

    # MinerU typically creates a subdirectory named after the input file
    # Walk through all subdirectories to find output files
    for root, dirs, files in os.walk(output_dir):
        root_path = Path(root)
        for f in files:
            fp = root_path / f
            if md_path is None and fp.suffix in (".md", ".markdown"):
                md_path = fp
            if json_path is None and fp.suffix == ".json":
                json_path = fp
        for d in dirs:
            if d.lower() in ("images", "imgs", "pictures"):
                images_dir = root_path / d

    return md_path, json_path, images_dir


def parse_with_mineru(input_path: str, output_dir: Optional[str] = None) -> ParsedDocument:
    """Parse a document using MinerU and return the extracted content.

    Args:
        input_path: Path to the input file (PDF, DOCX, PPTX, XLSX, image).
        output_dir: Output directory for MinerU results. Auto-generated if None.

    Returns:
        ParsedDocument with text, markdown_path, json_path, images_dir, parser, warnings.

    Raises:
        FileNotFoundError: If input_path does not exist.
        RuntimeError: If MinerU is not installed or parsing fails.
    """
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    cmd_name = _pick_command()
    if cmd_name is None:
        raise RuntimeError(
            "MinerU is not installed. Please run: "
            "powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1"
        )

    if output_dir is None:
        uid = uuid.uuid4().hex[:12]
        output_dir = os.path.join(MINERU_OUTPUT_BASE, uid)

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    cmd = _build_command(cmd_name, input_path, output_dir)
    logger.info(f"MinerU parse: cmd={cmd_name} input={input_path} output={output_dir}")

    warnings: list[str] = []

    timeout = _get_settings().mineru_timeout_seconds if _get_settings else int(os.getenv("MINERU_TIMEOUT_SECONDS", "300"))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        stderr_text = result.stderr.strip()
        stdout_text = result.stdout.strip()

        if stderr_text:
            # MinerU often prints progress to stderr, not necessarily errors
            logger.info(f"MinerU stderr (first 300 chars): {stderr_text[:300]}")

        if result.returncode != 0:
            error_detail = (stderr_text or stdout_text or f"exit code {result.returncode}")[:500]
            logger.error(f"MinerU failed: {error_detail}")
            raise RuntimeError(f"MinerU parsing failed: {error_detail}")

    except subprocess.TimeoutExpired:
        timeout_val = _get_settings().mineru_timeout_seconds if _get_settings else int(os.getenv("MINERU_TIMEOUT_SECONDS", "300"))
        raise RuntimeError(
            f"MinerU timed out after {timeout_val}s. "
            "Try increasing MINERU_TIMEOUT_SECONDS in .env for large documents."
        )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"MinerU execution error: {e}")

    # Find output files
    out_dir = Path(output_dir)
    md_path, json_path, images_dir = _find_output_files(out_dir)

    text = ""
    if md_path is not None:
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
            logger.info(f"MinerU read .md: {md_path} ({len(text)} chars)")
        except Exception as e:
            warnings.append(f"Failed to read markdown output: {e}")
    elif json_path is not None:
        try:
            import json as _json
            data = _json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
            # Extract text from MinerU JSON format
            if isinstance(data, list):
                text_parts = []
                for item in data:
                    if isinstance(item, dict):
                        text_parts.append(item.get("text", "") or _json.dumps(item, ensure_ascii=False))
                    elif isinstance(item, str):
                        text_parts.append(item)
                text = "\n\n".join(text_parts)
            elif isinstance(data, dict):
                text = data.get("content", "") or _json.dumps(data, ensure_ascii=False, indent=2)
            else:
                text = str(data)
            logger.info(f"MinerU read .json: {json_path} ({len(text)} chars)")
        except Exception as e:
            warnings.append(f"Failed to read json output: {e}")
            raise RuntimeError(f"MinerU output could not be read: {e}")
    else:
        # List what was actually produced for debugging
        produced = list(out_dir.rglob("*"))
        produced_str = ", ".join(str(p.relative_to(out_dir)) for p in produced[:20])
        logger.error(f"MinerU produced no .md or .json. Files: {produced_str}")
        raise RuntimeError(
            f"MinerU produced no readable output. Files in output dir: {produced_str}"
        )

    if not text.strip():
        warnings.append(
            "解析结果为空。可能是扫描件或图片型 PDF，"
            "建议尝试 MINERU_METHOD=ocr 或 MINERU_BACKEND=hybrid-auto-engine。"
        )
    elif len(text.strip()) < 50:
        warnings.append(
            f"解析文本过短（仅 {len(text.strip())} 字符）。"
            "可能是扫描件或图片型 PDF，建议尝试 MINERU_METHOD=ocr 或 MINERU_BACKEND=hybrid-auto-engine。"
        )

    return ParsedDocument(
        text=text,
        markdown_path=str(md_path) if md_path else None,
        json_path=str(json_path) if json_path else None,
        images_dir=str(images_dir) if images_dir else None,
        parser=cmd_name,
        warnings=warnings,
    )


# Re-export the deprecated async stub for backward compatibility
# (old code that called parse_document_with_mineru will get a clear error)
async def parse_document_with_mineru(file_path: str) -> str:
    """Deprecated: use parse_with_mineru() instead."""
    try:
        result = parse_with_mineru(file_path)
        return result.text
    except RuntimeError as e:
        raise NotImplementedError(str(e))
